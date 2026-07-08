"""Query Planner: LLM produces a structured ExecutionPlan (never SQL).

Every table/column in the plan is validated against the resolved metadata -
hallucinated identifiers are stripped and lower the metadata confidence.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LLMUnavailable
from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.models.catalog import CatalogRelationship, CatalogTable
from app.pipeline.types import ExecutionPlan, PipelineContext

logger = get_logger(__name__)


class QueryPlanner:
    async def run(self, ctx: PipelineContext, db: AsyncSession) -> None:
        if not ctx.resolved_tables:
            ctx.plan = ExecutionPlan(rationale="No matching tables found in the catalog.")
            ctx.confidence["sql"] = 0.0
            return

        schema_context = self._schema_context(ctx)
        relationships = await self._relationship_context(ctx, db)
        history = ""
        if ctx.previous_plan and ctx.intent and ctx.intent.is_follow_up:
            history = (
                "This is a FOLLOW-UP. Previous execution plan (modify it per the new message, "
                f"keep everything else):\n{ctx.previous_plan.model_dump_json()}\n\n"
            )

        user_block = (
            f"{history}"
            f"Question: {ctx.effective_prompt}\n\n"
            f"Intent analysis: {ctx.intent.model_dump_json() if ctx.intent else '{}'}\n\n"
            f"Business glossary context: {json.dumps(ctx.glossary_context)}\n\n"
            f"Defined business metrics: {json.dumps(ctx.metric_context)}\n\n"
            f"Available schema:\n{schema_context}\n\n"
            f"Known relationships:\n{relationships or '(none declared)'}"
        )

        try:
            llm = get_llm()
            parsed, result = await llm.complete_json(prompts.PLANNER_SYSTEM, user_block)
            ctx.record_llm("plan", result)
        except LLMUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("planner LLM failed: %s", exc)
            parsed = {}

        plan = self._parse_plan(parsed)
        hallucinated = self._validate_references(plan, ctx)
        if hallucinated:
            ctx.warnings.append(
                "Removed unknown identifiers proposed by the model: " + ", ".join(sorted(hallucinated))
            )
            plan.confidence = max(plan.confidence - 0.2 * len(hallucinated), 0.1)
        ctx.plan = plan
        ctx.confidence["sql"] = plan.confidence

    @staticmethod
    def _schema_context(ctx: PipelineContext) -> str:
        blocks = []
        for table in ctx.resolved_tables:
            cols = "\n".join(
                f"  - {c['name']} ({c['data_type']})"
                + (" [PARTITION]" if c["is_partition"] else "")
                + (f": {c['description']}" if c.get("description") else "")
                + (f" e.g. {c['sample_values']}" if c.get("sample_values") else "")
                for c in table.columns
            )
            row_info = f", ~{table.row_count:,} rows" if table.row_count else ""
            blocks.append(
                f"TABLE {table.qualified_name}{row_info}"
                + (f" - {table.description}" if table.description else "")
                + f"\n{cols}"
            )
        return "\n\n".join(blocks)

    async def _relationship_context(self, ctx: PipelineContext, db: AsyncSession) -> str:
        table_ids = {t.id: t.qualified_name for t in ctx.resolved_tables}
        if not table_ids:
            return ""
        rows = (
            await db.execute(
                select(CatalogRelationship).where(
                    CatalogRelationship.from_table_id.in_(table_ids),
                    CatalogRelationship.to_table_id.in_(table_ids),
                    CatalogRelationship.is_approved.is_(True),
                )
            )
        ).scalars().all()
        return "\n".join(
            f"{table_ids[r.from_table_id]}.{r.from_column} -> "
            f"{table_ids[r.to_table_id]}.{r.to_column} ({r.relationship_type})"
            for r in rows
        )

    @staticmethod
    def _parse_plan(parsed: dict) -> ExecutionPlan:
        if not parsed:
            return ExecutionPlan(rationale="Planner produced no output.", confidence=0.1)
        try:
            fields = {k: v for k, v in parsed.items() if k in ExecutionPlan.model_fields}
            return ExecutionPlan(**fields)
        except Exception as exc:  # noqa: BLE001
            logger.warning("plan parse failed: %s", exc)
            return ExecutionPlan(rationale=f"Unparseable plan: {exc}", confidence=0.1)

    @staticmethod
    def _validate_references(plan: ExecutionPlan, ctx: PipelineContext) -> set[str]:
        """Strip tables/columns not present in resolved metadata (anti-hallucination)."""
        known_tables = {t.qualified_name.lower() for t in ctx.resolved_tables}
        known_columns: set[str] = set()
        for table in ctx.resolved_tables:
            for col in table.columns:
                known_columns.add(f"{table.qualified_name}.{col['name']}".lower())

        removed: set[str] = set()

        def col_ok(qualified: str) -> bool:
            q = qualified.lower()
            if q in known_columns:
                return True
            # allow alias references (no dots) used in order_by
            return "." not in q

        plan.tables = [t for t in plan.tables if t.lower() in known_tables or removed.add(t)]
        plan.columns = [c for c in plan.columns if col_ok(c) or removed.add(c)]
        plan.group_by = [c for c in plan.group_by if col_ok(c) or removed.add(c)]
        plan.filters = [f for f in plan.filters if col_ok(f.column) or removed.add(f.column)]
        plan.aggregations = [
            a for a in plan.aggregations
            if a.column == "*" or col_ok(a.column) or removed.add(a.column)
        ]
        plan.joins = [
            j for j in plan.joins
            if (
                j.left_table.lower() in known_tables
                and j.right_table.lower() in known_tables
                and col_ok(f"{j.left_table}.{j.left_column}")
                and col_ok(f"{j.right_table}.{j.right_column}")
            ) or removed.add(f"{j.left_table}<->{j.right_table}")
        ]
        removed.discard(None)  # the .add() trick inserts None
        return removed
