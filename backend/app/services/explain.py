"""Explain SQL service: business-language rationale for any query."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.schemas.response import SqlExplanation

logger = get_logger(__name__)


class ExplainService:
    async def explain(self, sql: str, dialect: str = "hive",
                      question: str | None = None) -> SqlExplanation:
        deterministic = self._structural_explanation(sql, dialect)
        try:
            llm = get_llm()
            parsed, _ = await llm.complete_json(
                prompts.EXPLAIN_SQL_SYSTEM,
                (f"Original question: {question}\n\n" if question else "") + f"SQL:\n{sql}",
            )
            if parsed.get("summary"):
                return SqlExplanation(
                    summary=str(parsed.get("summary", "")),
                    table_reasons=[str(r) for r in parsed.get("table_reasons", [])] or deterministic.table_reasons,
                    filter_reasons=[str(r) for r in parsed.get("filter_reasons", [])] or deterministic.filter_reasons,
                    aggregation_reasons=[str(r) for r in parsed.get("aggregation_reasons", [])] or deterministic.aggregation_reasons,
                    grouping_reasons=[str(r) for r in parsed.get("grouping_reasons", [])] or deterministic.grouping_reasons,
                )
        except Exception as exc:  # noqa: BLE001 - fall back to structural
            logger.debug("LLM explanation unavailable: %s", exc)
        return deterministic

    @staticmethod
    def _structural_explanation(sql: str, dialect: str) -> SqlExplanation:
        explanation = SqlExplanation(summary="Structural breakdown of the query.")
        try:
            tree = sqlglot.parse_one(sql, read=dialect)
        except Exception:  # noqa: BLE001
            explanation.summary = "The SQL could not be parsed for a structural explanation."
            return explanation

        tables = [
            ".".join(p for p in [t.db, t.name] if p) for t in tree.find_all(exp.Table)
        ]
        if tables:
            explanation.table_reasons = [f"Reads from {t}" for t in dict.fromkeys(tables)]
        for join in tree.find_all(exp.Join):
            on = join.args.get("on")
            explanation.table_reasons.append(
                f"Joins {join.this.sql(dialect=dialect)}"
                + (f" on {on.sql(dialect=dialect)}" if on else "")
            )
        where = tree.args.get("where") if isinstance(tree, exp.Select) else None
        if where:
            explanation.filter_reasons = [
                f"Filters rows where {where.this.sql(dialect=dialect)}"
            ]
        for agg in tree.find_all(exp.AggFunc):
            explanation.aggregation_reasons.append(f"Computes {agg.sql(dialect=dialect)}")
        group = tree.args.get("group") if isinstance(tree, exp.Select) else None
        if group:
            explanation.grouping_reasons = [
                f"Groups results by {', '.join(g.sql(dialect=dialect) for g in group.expressions)}"
            ]
        explanation.summary = (
            f"The query reads {len(set(tables))} table(s)"
            + (", applies filters" if where else "")
            + (", aggregates measures" if explanation.aggregation_reasons else "")
            + (" and groups the output" if group else "")
            + "."
        )
        return explanation


explain_service = ExplainService()
