"""SQL Generator: converts the validated ExecutionPlan into dialect SQL.

Primary path uses the LLM constrained to the plan + schema. A deterministic
builder handles straightforward plans and serves as graceful degradation when
the LLM is unavailable.
"""
from __future__ import annotations

import json

from app.connectors.base import IAnalyticsConnector
from app.core.exceptions import LLMUnavailable, ValidationFailed
from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.pipeline.types import ExecutionPlan, PipelineContext

logger = get_logger(__name__)

_RELATIVE_HIVE = {
    "relative:last_7_days": "date_sub(current_date, 7)",
    "relative:last_30_days": "date_sub(current_date, 30)",
    "relative:last_90_days": "date_sub(current_date, 90)",
    "relative:last_month": "add_months(current_date, -1)",
    "relative:last_3_months": "add_months(current_date, -3)",
    "relative:last_6_months": "add_months(current_date, -6)",
    "relative:last_12_months": "add_months(current_date, -12)",
    "relative:last_year": "add_months(current_date, -12)",
    "relative:ytd": "trunc(current_date, 'YYYY')",
}

_AGG_SQL = {
    "sum": "SUM({c})", "avg": "AVG({c})", "count": "COUNT({c})",
    "count_distinct": "COUNT(DISTINCT {c})", "min": "MIN({c})", "max": "MAX({c})",
    "median": "PERCENTILE_APPROX({c}, 0.5)", "stddev": "STDDEV({c})", "variance": "VARIANCE({c})",
}


class SQLGenerator:
    async def run(self, ctx: PipelineContext, connector: IAnalyticsConnector) -> None:
        plan = ctx.plan
        if plan is None or not plan.tables:
            raise ValidationFailed(
                "I couldn't map your question to any known tables. "
                "Try mentioning the dataset, or check the Metadata Manager for available data.",
                detail={"rationale": plan.rationale if plan else ""},
            )

        dialect_name = connector.dialect.sqlglot_dialect
        try:
            llm = get_llm()
            system = prompts.SQL_SYSTEM.format(
                dialect=dialect_name.upper(),
                dialect_hints=connector.dialect.dialect_hints(),
            )
            schema_context = "\n".join(
                f"{t.qualified_name}: {', '.join(c['name'] for c in t.columns)}"
                for t in ctx.resolved_tables
            )
            parsed, result = await llm.complete_json(
                system,
                f"Execution plan:\n{plan.model_dump_json(indent=2)}\n\n"
                f"Schema (only these identifiers exist):\n{schema_context}\n\n"
                f"Relative date translations: {json.dumps(_RELATIVE_HIVE)}",
            )
            ctx.record_llm("sql", result)
            sql = (parsed.get("sql") or "").strip().rstrip(";")
            if sql:
                ctx.sql = sql
                if parsed.get("explanation"):
                    plan.rationale = plan.rationale or str(parsed["explanation"])
                return
            logger.warning("LLM returned empty SQL, using deterministic builder")
        except LLMUnavailable:
            ctx.warnings.append("LLM unavailable for SQL generation; used deterministic plan builder.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("SQL LLM failed (%s); using deterministic builder", exc)

        ctx.sql = self.build_deterministic(plan)

    @staticmethod
    def build_deterministic(plan: ExecutionPlan) -> str:
        """Assemble SQL directly from the plan - no LLM involved."""
        def qident(qualified: str) -> str:
            return ".".join(f"`{p}`" for p in qualified.split("."))

        def col_ref(qualified: str) -> str:
            # db.table.column -> `db`.`table`.`column`; bare aliases pass through
            return qident(qualified) if "." in qualified else f"`{qualified}`"

        select_parts: list[str] = [col_ref(c) + f" AS `{c.split('.')[-1]}`" for c in plan.columns]
        for agg in plan.aggregations:
            template = _AGG_SQL.get(agg.function.lower(), "SUM({c})")
            target = "*" if agg.column == "*" else col_ref(agg.column)
            alias = agg.alias or f"{agg.function}_{agg.column.split('.')[-1]}".replace("*", "all")
            select_parts.append(template.format(c=target) + f" AS `{alias}`")
        if not select_parts:
            select_parts = ["*"]

        base_table = plan.tables[0]
        sql = f"SELECT {', '.join(select_parts)}\nFROM {qident(base_table)}"

        joined = {base_table.lower()}
        for join in plan.joins:
            target = join.right_table if join.right_table.lower() not in joined else join.left_table
            if target.lower() in joined:
                continue
            joined.add(target.lower())
            jt = {"inner": "JOIN", "left": "LEFT JOIN", "right": "RIGHT JOIN", "full": "FULL OUTER JOIN"}
            sql += (
                f"\n{jt.get(join.join_type, 'JOIN')} {qident(target)} ON "
                f"{qident(join.left_table)}.`{join.left_column}` = "
                f"{qident(join.right_table)}.`{join.right_column}`"
            )

        conditions = []
        for f in plan.filters:
            column = col_ref(f.column)
            op = f.operator.lower()
            value = f.value
            if isinstance(value, str) and value in _RELATIVE_HIVE:
                conditions.append(f"{column} >= {_RELATIVE_HIVE[value]}")
            elif op in ("is_null", "is_not_null"):
                conditions.append(f"{column} IS {'NOT ' if op == 'is_not_null' else ''}NULL")
            elif op in ("in", "not_in") and isinstance(value, list):
                rendered = ", ".join(_lit(v) for v in value)
                conditions.append(f"{column} {'NOT IN' if op == 'not_in' else 'IN'} ({rendered})")
            elif op == "between" and isinstance(value, list) and len(value) == 2:
                conditions.append(f"{column} BETWEEN {_lit(value[0])} AND {_lit(value[1])}")
            elif op == "like":
                conditions.append(f"{column} LIKE {_lit(value)}")
            else:
                sql_op = {"=": "=", "!=": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<="}.get(op, "=")
                conditions.append(f"{column} {sql_op} {_lit(value)}")
        if conditions:
            sql += "\nWHERE " + "\n  AND ".join(conditions)

        if plan.group_by:
            sql += "\nGROUP BY " + ", ".join(col_ref(c) for c in plan.group_by)
        if plan.order_by:
            parts = [
                f"{col_ref(o.get('column', ''))} {'DESC' if str(o.get('direction', 'desc')).lower() == 'desc' else 'ASC'}"
                for o in plan.order_by if o.get("column")
            ]
            if parts:
                sql += "\nORDER BY " + ", ".join(parts)
        if plan.limit:
            sql += f"\nLIMIT {int(plan.limit)}"
        return sql


def _lit(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"
