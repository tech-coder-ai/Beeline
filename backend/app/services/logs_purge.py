"""Purge operational logs and analytics from the metadata repository."""
from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import SyncRun
from app.models.chat import ChatMessage, ExecutionHistory, Feedback
from app.models.dashboard import DashboardWidget
from app.models.governance import AuditLog


async def _count(db: AsyncSession, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar() or 0


async def purge_executions(db: AsyncSession) -> dict[str, int]:
    """Remove execution history and dependent feedback rows."""
    counts = {
        "execution_history": await _count(db, ExecutionHistory),
        "feedback": await _count(db, Feedback),
    }
    await db.execute(
        update(ChatMessage).where(ChatMessage.execution_id.isnot(None)).values(execution_id=None)
    )
    await db.execute(
        update(DashboardWidget)
        .where(DashboardWidget.source_execution_id.isnot(None))
        .values(source_execution_id=None)
    )
    await db.execute(delete(Feedback))
    await db.execute(delete(ExecutionHistory))
    return counts


async def purge_audit(db: AsyncSession) -> dict[str, int]:
    counts = {"audit_logs": await _count(db, AuditLog)}
    await db.execute(delete(AuditLog))
    return counts


async def purge_sync_runs(db: AsyncSession) -> dict[str, int]:
    counts = {"sync_runs": await _count(db, SyncRun)}
    await db.execute(delete(SyncRun))
    return counts


async def purge_all(db: AsyncSession, *, include_sync_runs: bool = False) -> dict[str, int]:
    deleted: dict[str, int] = {}
    deleted.update(await purge_executions(db))
    if include_sync_runs:
        deleted.update(await purge_sync_runs(db))
    deleted.update(await purge_audit(db))
    return deleted
