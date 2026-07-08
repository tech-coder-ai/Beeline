"""Audit trail helper - every significant action lands in audit_logs."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance import AuditLog


async def audit(
    db: AsyncSession,
    user_id: str,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    detail: dict | None = None,
    severity: str = "info",
) -> None:
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail or {},
        severity=severity,
    ))
