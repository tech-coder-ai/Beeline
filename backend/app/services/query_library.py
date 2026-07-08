"""SQL Knowledge Library: successful queries are captured and reused."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queries import QueryLibraryEntry
from app.pipeline.types import PipelineContext


def normalize_question(text: str) -> str:
    return " ".join(text.lower().split())


class QueryLibraryService:
    async def record_success(self, ctx: PipelineContext, db: AsyncSession) -> None:
        sql = ctx.optimized_sql or ctx.sql
        if not sql:
            return
        normalized = normalize_question(ctx.effective_prompt)

        if ctx.library_match:
            entry = await db.get(QueryLibraryEntry, ctx.library_match.entry_id)
            if entry:
                entry.success_count += 1
                if ctx.execution_time_ms:
                    prev = entry.avg_execution_ms or ctx.execution_time_ms
                    entry.avg_execution_ms = round(0.7 * prev + 0.3 * ctx.execution_time_ms, 1)
                return

        existing = (
            await db.execute(
                select(QueryLibraryEntry).where(
                    QueryLibraryEntry.normalized_question == normalized,
                    QueryLibraryEntry.connector_id == ctx.connector_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.sql = sql
            existing.success_count += 1
            existing.is_active = True
            return

        db.add(QueryLibraryEntry(
            question=ctx.effective_prompt,
            normalized_question=normalized,
            sql=sql,
            connector_id=ctx.connector_id,
            tables_used=ctx.plan.tables if ctx.plan else [],
            intent=ctx.intent.model_dump() if ctx.intent else None,
            execution_plan=ctx.plan.model_dump() if ctx.plan else None,
            avg_execution_ms=float(ctx.execution_time_ms) if ctx.execution_time_ms else None,
        ))

    async def apply_feedback(self, db: AsyncSession, execution_id: str, positive: bool) -> None:
        """Feedback loop: repeated negatives deactivate a library entry."""
        from app.models.chat import ExecutionHistory

        history = await db.get(ExecutionHistory, execution_id)
        if not history or not history.reused_query_id:
            return
        entry = await db.get(QueryLibraryEntry, history.reused_query_id)
        if not entry:
            return
        if positive:
            entry.positive_feedback += 1
        else:
            entry.negative_feedback += 1
            if entry.negative_feedback >= 3 and entry.negative_feedback > entry.positive_feedback:
                entry.is_active = False
