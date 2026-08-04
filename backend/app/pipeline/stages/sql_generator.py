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
from app.llm.trace import complete_json_traced
from app.pipeline.sql_utils import sanitize_sql
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
            system = prompts.SQL_SYSTEM.format(
                dialect=dialect_name.upper(),
                dialect_hints=connector.dialect.dialect_hints(),
            )
            schema_context = "\n".join(
                f"{t.qualified_name}:\n"
                + "\n".join(
                    f"  - {c['name']} ({c['data_type']})"
                    + (f": {c['description']}" if c.get("description") else "")
                    for c in t.columns
                )
                for t in ctx.resolved_tables
            )
            user_message = (
                f"Execution plan:\n{plan.model_dump_json(indent=2)}\n\n"
                f"Schema (only these identifiers exist):\n{schema_context}\n\n"
                f"Relative date translations: {json.dumps(_RELATIVE_HIVE)}"
            )
            parsed, _ = await complete_json_traced(ctx, "sql", system, user_message)
            sql = sanitize_sql((parsed.get("sql") or "").strip().rstrip(";"), dialect_name)
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

        ctx.sql = self.build_deterministic(plan, self._column_types(ctx))

    @staticmethod
    def _column_types(ctx: PipelineContext) -> dict[str, str]:
        types: dict[str, str] = {}
        for table in ctx.resolved_tables:
            for col in table.columns:
                name = str(col.get("name", ""))
                data_type = str(col.get("data_type", ""))
                if not name or not data_type:
                    continue
                qualified = f"{table.qualified_name}.{name}".lower()
                types[qualified] = data_type
                types[name.lower()] = data_type
        return types

    @staticmethod
    def build_deterministic(plan: ExecutionPlan, column_types: dict[str, str] | None = None) -> str:
        """Assemble SQL directly from the plan - no LLM involved."""
        column_types = column_types or {}
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
            column_type = _resolve_column_type(f.column, column_types)
            compare_column = _comparison_column_ref(column, column_type)
            op = f.operator.lower()
            value = f.value
            if isinstance(value, str) and value in _RELATIVE_HIVE:
                conditions.append(f"{compare_column} >= {_RELATIVE_HIVE[value]}")
            elif op in ("is_null", "is_not_null"):
                conditions.append(f"{compare_column} IS {'NOT ' if op == 'is_not_null' else ''}NULL")
            elif op in ("in", "not_in") and isinstance(value, list):
                rendered = ", ".join(_lit(v, column_type) for v in value)
                conditions.append(f"{compare_column} {'NOT IN' if op == 'not_in' else 'IN'} ({rendered})")
            elif op == "between" and isinstance(value, list) and len(value) == 2:
                conditions.append(
                    f"{compare_column} BETWEEN {_lit(value[0], column_type)} AND {_lit(value[1], column_type)}"
                )
            elif op == "like":
                conditions.append(f"{compare_column} LIKE {_lit(value, column_type)}")
            else:
                sql_op = {"=": "=", "!=": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<="}.get(op, "=")
                conditions.append(f"{compare_column} {sql_op} {_lit(value, column_type)}")
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


def _lit(value, column_type: str | None = None) -> str:
    if value is None:
        return "NULL"
    if _is_boolean_type(column_type):
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return "1" if value else "0"
        if isinstance(value, str) and value.strip().lower() in {"true", "yes", "false", "no"}:
            return "1" if value.strip().lower() in {"true", "yes"} else "0"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _resolve_column_type(column: str, column_types: dict[str, str]) -> str | None:
    if not column:
        return None
    key = column.lower()
    if key in column_types:
        return column_types[key]
    if "." in column:
        short_key = column.rsplit(".", 1)[-1].lower()
        return column_types.get(short_key)
    return None


def _comparison_column_ref(column: str, column_type: str | None) -> str:
    if _is_clob_type(column_type):
        return f"CAST({column} AS STRING)"
    return column


def _is_clob_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    lowered = data_type.lower()
    return "clob" in lowered or "nclob" in lowered or "longvarchar" in lowered or lowered == "text"


def _is_boolean_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    lowered = data_type.lower()
    return "boolean" in lowered or lowered == "bool"
