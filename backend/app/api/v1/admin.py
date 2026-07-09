"""Admin API: connectors, sync, enrichment, config, logs, health."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import (
    available_types,
    close_all,
    default_connector_id,
    get_connector,
    list_connector_ids,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import NotFound, ValidationFailed
from app.models.catalog import SyncRun
from app.models.chat import ExecutionHistory
from app.models.governance import AuditLog
from app.schemas.api import (
    ConfigUpdate,
    ConnectorTestResult,
    ConnectorUpsert,
    EnrichRequest,
    SyncRequest,
)
from app.services.audit import audit
from app.services.enrichment import enrichment_service
from app.services.logs_purge import purge_all, purge_audit, purge_executions
from app.services.metadata_sync import metadata_sync_service

router = APIRouter(prefix="/admin", tags=["admin"])
health_router = APIRouter(tags=["health"])

_REDACT = ("password", "api_key", "secret", "token", "keytab_path", "krb5_ccache")


def _redact(value):
    if isinstance(value, dict):
        return {
            k: ("***" if any(s in k.lower() for s in _REDACT) and v else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


# ------------------------------------------------------------------ connectors
@router.get("/connectors")
async def connectors():
    settings = get_settings()
    definitions = settings.section("connectors.definitions")
    return {
        "default": default_connector_id(),
        "available_types": available_types(),
        "connectors": [
            {"id": cid, **_redact(cfg)} for cid, cfg in definitions.items()
        ],
    }


@router.post("/connectors")
async def upsert_connector(body: ConnectorUpsert, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    cid = body.id.strip()
    if not cid:
        raise ValidationFailed("Connector id is required")
    if not body.type:
        raise ValidationFailed("Connector type is required")
    cfg = body.model_dump(exclude={"id"})
    definitions = settings.raw.setdefault("connectors", {}).setdefault("definitions", {})
    existing = definitions.get(cid, {})
    if not cfg.get("password") and existing.get("password"):
        cfg["password"] = existing["password"]
    definitions[cid] = cfg
    await close_all()
    await audit(db, "default", "admin.connector_upsert", detail={"id": cid, "type": body.type})
    await db.commit()
    return {"id": cid}


@router.put("/connectors/{connector_id}/default")
async def set_default_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    if connector_id not in settings.section("connectors.definitions"):
        raise NotFound(f"Connector '{connector_id}' is not configured")
    settings.raw.setdefault("connectors", {})["default"] = connector_id
    await audit(db, "default", "admin.connector_default", detail={"connector_id": connector_id})
    await db.commit()
    return {"default": connector_id}


@router.post("/connectors/{connector_id}/test", response_model=ConnectorTestResult)
async def test_connector(connector_id: str):
    import time

    connector = get_connector(connector_id)
    started = time.monotonic()
    ok, message = await connector.test_connection()
    return ConnectorTestResult(
        ok=ok, message=message, latency_ms=int((time.monotonic() - started) * 1000)
    )


# ------------------------------------------------------------------ sync & enrichment
@router.post("/sync")
async def trigger_sync(request: SyncRequest, db: AsyncSession = Depends(get_db)):
    await audit(db, "default", "admin.sync_trigger", detail=request.model_dump())
    await db.commit()
    task = asyncio.create_task(
        metadata_sync_service.sync(request.connector_id, request.mode)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"started": True, "mode": request.mode}


_background_tasks: set[asyncio.Task] = set()


@router.get("/sync/runs")
async def sync_runs(db: AsyncSession = Depends(get_db)):
    runs = (
        await db.execute(select(SyncRun).order_by(SyncRun.created_at.desc()).limit(30))
    ).scalars().all()
    return [
        {c: getattr(r, c) for c in (
            "id", "connector_id", "mode", "status", "tables_synced",
            "columns_synced", "error", "created_at", "finished_at",
        )}
        for r in runs
    ]


@router.post("/enrich")
async def trigger_enrichment(request: EnrichRequest, db: AsyncSession = Depends(get_db)):
    result = await enrichment_service.enrich_tables(db, request.table_ids or None)
    await audit(db, "default", "admin.enrich_trigger", detail=result)
    await db.commit()
    return result


# ------------------------------------------------------------------ config
@router.get("/config")
async def get_config():
    """Full effective configuration (secrets redacted)."""
    return _redact(get_settings().raw)


@router.put("/config")
async def update_config(update: ConfigUpdate, db: AsyncSession = Depends(get_db)):
    """Runtime config override (in-memory + audited). File remains source of truth."""
    settings = get_settings()
    node = settings.raw
    path = update.key.split(".")
    for part in path[:-1]:
        node = node.setdefault(part, {})
    node[path[-1]] = update.value
    if update.key.startswith("connectors."):
        await close_all()
    await audit(db, "default", "admin.config_change",
                detail={"key": update.key, "value": update.value}, severity="warning")
    await db.commit()
    return {"key": update.key, "value": update.value}


@router.get("/feature-flags")
async def feature_flags():
    return get_settings().section("feature_flags")


# ------------------------------------------------------------------ logs & analytics
@router.get("/logs/audit")
async def audit_logs(action: str | None = None, severity: str | None = None,
                     limit: int = 100, db: AsyncSession = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if severity:
        stmt = stmt.where(AuditLog.severity == severity)
    logs = (await db.execute(stmt)).scalars().all()
    return [
        {c: getattr(l, c) for c in (
            "id", "user_id", "action", "entity_type", "entity_id",
            "detail", "severity", "created_at",
        )}
        for l in logs
    ]


@router.get("/logs/executions")
async def execution_logs(status: str | None = None, search: str | None = None,
                         limit: int = 100, db: AsyncSession = Depends(get_db)):
    stmt = select(ExecutionHistory).order_by(ExecutionHistory.created_at.desc()).limit(min(limit, 500))
    if status:
        stmt = stmt.where(ExecutionHistory.status == status)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            ExecutionHistory.prompt.ilike(pattern) | ExecutionHistory.optimized_sql.ilike(pattern)
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {c: getattr(e, c) for c in (
            "id", "prompt", "status", "optimized_sql", "row_count", "execution_time_ms",
            "confidence", "warnings", "error", "llm_model", "created_at",
        )}
        for e in rows
    ]


@router.get("/analytics/usage")
async def usage_analytics(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(ExecutionHistory.id)))).scalar() or 0
    by_status = (
        await db.execute(
            select(ExecutionHistory.status, func.count()).group_by(ExecutionHistory.status)
        )
    ).all()
    avg_ms = (
        await db.execute(
            select(func.avg(ExecutionHistory.execution_time_ms))
            .where(ExecutionHistory.execution_time_ms.isnot(None))
        )
    ).scalar()
    return {
        "total_queries": total,
        "by_status": {status: count for status, count in by_status},
        "avg_execution_ms": round(avg_ms, 1) if avg_ms else None,
    }


@router.delete("/logs/executions")
async def clear_execution_logs(confirm: bool = False, db: AsyncSession = Depends(get_db)):
    if not confirm:
        raise ValidationFailed("Pass confirm=true to clear execution history and analytics")
    deleted = await purge_executions(db)
    await db.commit()
    return {"deleted": deleted}


@router.delete("/logs/audit")
async def clear_audit_logs(confirm: bool = False, db: AsyncSession = Depends(get_db)):
    if not confirm:
        raise ValidationFailed("Pass confirm=true to clear the audit trail")
    deleted = await purge_audit(db)
    await db.commit()
    return {"deleted": deleted}


@router.delete("/logs")
async def clear_logs_and_analytics(
    confirm: bool = False,
    include_sync_runs: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Clear execution history, usage analytics, and audit logs."""
    if not confirm:
        raise ValidationFailed("Pass confirm=true to clear logs and analytics")
    deleted = await purge_all(db, include_sync_runs=include_sync_runs)
    await db.commit()
    return {"deleted": deleted}


# ------------------------------------------------------------------ health
@health_router.get("/health")
async def health():
    return {"status": "ok", "app": get_settings().get("app.name", "Beeline")}


@health_router.get("/health/deep")
async def deep_health(db: AsyncSession = Depends(get_db)):
    checks = {"api": "ok"}
    try:
        await db.execute(select(func.count(AuditLog.id)))
        checks["metadata_repository"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["metadata_repository"] = f"error: {exc}"
    for cid in list_connector_ids():
        try:
            ok, message = await get_connector(cid).test_connection()
            checks[f"connector:{cid}"] = "ok" if ok else message
        except Exception as exc:  # noqa: BLE001
            checks[f"connector:{cid}"] = f"error: {exc}"
    return checks
