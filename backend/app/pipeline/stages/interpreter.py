"""Result Interpreter: turns raw rows into narrative insights.

Deterministic statistics always run; the LLM adds a business narrative when
available. Insights are grounded in computed numbers, never invented.
"""
from __future__ import annotations

import json

from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.pipeline.types import PipelineContext
from app.pipeline.stages.visualization import ColumnProfile, _to_number

logger = get_logger(__name__)

MAX_SAMPLE_ROWS = 30


class ResultInterpreter:
    async def run(self, ctx: PipelineContext) -> dict:
        """Returns dict(summary, insights, recommendations, follow_up_questions)."""
        deterministic = self._deterministic_insights(ctx)
        narrative = await self._llm_narrative(ctx)

        summary = narrative.get("summary") or deterministic["summary"]
        insights = (narrative.get("insights") or deterministic["insights"])[:4]
        recommendations = (narrative.get("recommendations") or [])[:3]
        follow_ups = (narrative.get("follow_up_questions") or deterministic["follow_ups"])[:3]
        return {
            "summary": summary,
            "insights": [str(i) for i in insights],
            "recommendations": [str(r) for r in recommendations],
            "follow_up_questions": [str(f) for f in follow_ups],
        }

    def _deterministic_insights(self, ctx: PipelineContext) -> dict:
        columns, rows = ctx.result_columns, ctx.result_rows
        insights: list[str] = []
        follow_ups: list[str] = []

        if not rows:
            return {
                "summary": "The query returned no rows for your criteria.",
                "insights": ["Try broadening the time range or removing a filter."],
                "follow_ups": [],
            }

        types = ctx.result_types or ["string"] * len(columns)
        col_values = [[r[i] if i < len(r) else None for r in rows] for i in range(len(columns))]
        profiles = [ColumnProfile(columns[i], types[i], col_values[i]) for i in range(len(columns))]
        numeric = [i for i, p in enumerate(profiles) if p.is_numeric]
        categorical = [i for i, p in enumerate(profiles) if p.is_categorical]
        temporal = [i for i, p in enumerate(profiles) if p.is_temporal]

        if numeric and len(rows) > 1:
            m = numeric[0]
            values = [(_to_number(r[m]) or 0, r) for r in rows]
            total = sum(v for v, _ in values)
            top_value, top_row = max(values, key=lambda pair: pair[0])
            label_idx = categorical[0] if categorical else (temporal[0] if temporal else None)
            top_label = str(top_row[label_idx]) if label_idx is not None else "the top row"
            metric_name = columns[m].replace("_", " ")
            if total:
                insights.append(
                    f"{top_label} leads with {top_value:,.0f} {metric_name} "
                    f"({100 * top_value / total:.1f}% of the {total:,.0f} total)."
                )
            low_value, low_row = min(values, key=lambda pair: pair[0])
            if label_idx is not None and low_row is not top_row:
                insights.append(
                    f"{low_row[label_idx]} is lowest at {low_value:,.0f} {metric_name}."
                )
            if temporal and len(rows) >= 3:
                ordered = sorted(rows, key=lambda r: str(r[temporal[0]]))
                first = _to_number(ordered[0][m]) or 0
                last = _to_number(ordered[-1][m]) or 0
                if first:
                    change = 100 * (last - first) / abs(first)
                    direction = "up" if change >= 0 else "down"
                    insights.append(
                        f"{metric_name} is {direction} {abs(change):.1f}% across the period "
                        f"({first:,.0f} → {last:,.0f})."
                    )
            follow_ups.append(f"What is driving {top_label}?")
            if temporal:
                follow_ups.append("Compare this with the previous period.")

        summary = (
            f"Returned {ctx.row_count:,} row(s)"
            + (f" in {ctx.execution_time_ms:,} ms" if ctx.execution_time_ms else "")
            + ("." if not insights else f". {insights[0]}")
        )
        return {"summary": summary, "insights": insights, "follow_ups": follow_ups}

    async def _llm_narrative(self, ctx: PipelineContext) -> dict:
        if not ctx.result_rows:
            return {}
        try:
            sample = {
                "columns": ctx.result_columns,
                "rows": ctx.result_rows[:MAX_SAMPLE_ROWS],
                "total_rows": ctx.row_count,
                "truncated_sample": len(ctx.result_rows) > MAX_SAMPLE_ROWS,
            }
            llm = get_llm()
            parsed, result = await llm.complete_json(
                prompts.INTERPRETER_SYSTEM,
                f"Question: {ctx.effective_prompt}\n\nSQL:\n{ctx.optimized_sql or ctx.sql}\n\n"
                f"Result sample:\n{json.dumps(sample, default=str)}",
            )
            ctx.record_llm("interpret", result)
            return parsed
        except Exception as exc:  # noqa: BLE001 - narrative is optional
            logger.debug("LLM narrative unavailable: %s", exc)
            return {}
