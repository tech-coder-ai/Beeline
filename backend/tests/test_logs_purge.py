"""Tests for logs/analytics purge."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.chat import ExecutionHistory, Feedback
from app.models.governance import AuditLog
from app.services.logs_purge import purge_all


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_purge_all_clears_logs_and_analytics(db_session: AsyncSession):
    execution = ExecutionHistory(prompt="test query", status="executed")
    db_session.add(execution)
    await db_session.flush()
    db_session.add(AuditLog(user_id="default", action="sql.execute", severity="info", detail={}))
    db_session.add(Feedback(execution_id=execution.id, user_id="default", rating="up"))
    await db_session.commit()

    deleted = await purge_all(db_session)
    await db_session.commit()

    assert deleted["execution_history"] == 1
    assert deleted["audit_logs"] == 1
    assert deleted["feedback"] == 1

    remaining_exec = (await db_session.execute(select(ExecutionHistory))).scalars().all()
    remaining_audit = (await db_session.execute(select(AuditLog))).scalars().all()
    remaining_feedback = (await db_session.execute(select(Feedback))).scalars().all()
    assert remaining_exec == []
    assert remaining_audit == []
    assert remaining_feedback == []
