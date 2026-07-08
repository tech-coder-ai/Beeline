"""Workspace API: dashboards, saved queries, feedback, SQL utilities."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors.registry import get_connector
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import NotFound
from app.models.chat import ExecutionHistory, Feedback
from app.models.dashboard import Dashboard, DashboardWidget
from app.models.queries import SavedQuery
from app.pipeline.stages.optimizer import SQLOptimizer
from app.pipeline.stages.validator import SQLValidator
from app.pipeline.stages.visualization import VisualizationPlanner
from app.pipeline.types import PipelineContext
from app.schemas.api import (
    DashboardIn,
    DashboardOut,
    FeedbackIn,
    SavedQueryIn,
    SavedQueryOut,
    SqlExecuteRequest,
    SqlValidateRequest,
    WidgetIn,
)
from app.services.audit import audit
from app.services.explain import explain_service
from app.services.query_library import QueryLibraryService

router = APIRouter(tags=["workspace"])
_validator = SQLValidator()
_optimizer = SQLOptimizer()
_viz = VisualizationPlanner()
_library = QueryLibraryService()


# ------------------------------------------------------------------ sql utilities
@router.post("/sql/validate")
async def validate_sql(request: SqlValidateRequest):
    connector = get_connector(request.connector_id)
    warnings = _validator.validate(request.sql, connector.dialect.sqlglot_dialect)
    return {"valid": True, "warnings": warnings}


@router.post("/sql/execute")
async def execute_sql(request: SqlExecuteRequest, db: AsyncSession = Depends(get_db)):
    """Direct SQL execution (used by saved queries & dashboard refresh).
    The same guard rails apply - SELECT only."""
    settings = get_settings()
    connector = get_connector(request.connector_id)
    dialect = connector.dialect.sqlglot_dialect
    _validator.validate(request.sql, dialect)
    ctx = PipelineContext(prompt="(direct sql)", connector_id=request.connector_id)
    sql = _optimizer.optimize(request.sql, dialect, ctx)
    max_rows = min(
        request.limit or settings.get("guardrails.max_result_rows", 10000),
        settings.get("guardrails.max_result_rows", 10000),
    )
    result = await connector.execute(
        sql, max_rows=max_rows,
        timeout_seconds=settings.get("guardrails.query_timeout_seconds", 300),
    )
    ctx.result_columns = result.columns
    ctx.result_types = result.column_types
    ctx.result_rows = result.rows
    ctx.row_count = result.row_count
    ctx.truncated = result.truncated
    viz = _viz.run(ctx)
    await audit(db, "default", "sql.execute_direct", detail={"sql": sql, "rows": result.row_count})
    await db.commit()
    return {
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "execution_time_ms": result.execution_time_ms,
        "truncated": result.truncated,
        "visualization": viz["visualization"],
        "charts": [c.model_dump() for c in viz["charts"]],
        "cards": [c.model_dump() for c in viz["cards"]],
        "table": viz["table"].model_dump() if viz["table"] else None,
        "sql": sql,
    }


@router.post("/sql/explain")
async def explain_sql(request: SqlValidateRequest):
    connector = get_connector(request.connector_id)
    explanation = await explain_service.explain(
        request.sql, connector.dialect.sqlglot_dialect, question=request.question
    )
    return explanation


# ------------------------------------------------------------------ saved queries
@router.get("/queries", response_model=list[SavedQueryOut])
async def list_saved_queries(db: AsyncSession = Depends(get_db)):
    return list((
        await db.execute(select(SavedQuery).order_by(SavedQuery.updated_at.desc()))
    ).scalars())


@router.post("/queries", response_model=SavedQueryOut)
async def save_query(query_in: SavedQueryIn, db: AsyncSession = Depends(get_db)):
    query = SavedQuery(**query_in.model_dump())
    db.add(query)
    await db.commit()
    return query


@router.patch("/queries/{query_id}/bookmark")
async def toggle_bookmark(query_id: str, db: AsyncSession = Depends(get_db)):
    query = await db.get(SavedQuery, query_id)
    if not query:
        raise NotFound("Saved query not found")
    query.is_bookmarked = not query.is_bookmarked
    await db.commit()
    return {"id": query_id, "is_bookmarked": query.is_bookmarked}


@router.delete("/queries/{query_id}")
async def delete_query(query_id: str, db: AsyncSession = Depends(get_db)):
    query = await db.get(SavedQuery, query_id)
    if not query:
        raise NotFound("Saved query not found")
    await db.delete(query)
    await db.commit()
    return {"deleted": query_id}


@router.post("/queries/{query_id}/run")
async def run_saved_query(query_id: str, db: AsyncSession = Depends(get_db)):
    query = await db.get(SavedQuery, query_id)
    if not query:
        raise NotFound("Saved query not found")
    result = await execute_sql(
        SqlExecuteRequest(sql=query.sql, connector_id=query.connector_id), db
    )
    query.run_count += 1
    query.last_run_at = datetime.now(timezone.utc)
    await db.commit()
    return result


# ------------------------------------------------------------------ dashboards
@router.get("/dashboards", response_model=list[DashboardOut])
async def list_dashboards(db: AsyncSession = Depends(get_db)):
    return list((
        await db.execute(
            select(Dashboard).options(selectinload(Dashboard.widgets))
            .order_by(Dashboard.updated_at.desc())
        )
    ).scalars())


@router.post("/dashboards", response_model=DashboardOut)
async def create_dashboard(dashboard_in: DashboardIn, db: AsyncSession = Depends(get_db)):
    dashboard = Dashboard(**dashboard_in.model_dump())
    db.add(dashboard)
    await db.commit()
    return DashboardOut(
        **dashboard_in.model_dump(), id=dashboard.id, is_shared=False, share_token=None,
        created_at=dashboard.created_at, updated_at=dashboard.updated_at, widgets=[],
    )


@router.get("/dashboards/{dashboard_id}", response_model=DashboardOut)
async def get_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    dashboard = (
        await db.execute(
            select(Dashboard).options(selectinload(Dashboard.widgets))
            .where(Dashboard.id == dashboard_id)
        )
    ).scalar_one_or_none()
    if not dashboard:
        raise NotFound("Dashboard not found")
    return dashboard


@router.post("/dashboards/{dashboard_id}/widgets")
async def add_widget(dashboard_id: str, widget_in: WidgetIn, db: AsyncSession = Depends(get_db)):
    dashboard = (
        await db.execute(
            select(Dashboard).options(selectinload(Dashboard.widgets))
            .where(Dashboard.id == dashboard_id)
        )
    ).scalar_one_or_none()
    if not dashboard:
        raise NotFound("Dashboard not found")
    widget = DashboardWidget(
        dashboard_id=dashboard_id, position=len(dashboard.widgets), **widget_in.model_dump()
    )
    db.add(widget)
    await db.commit()
    return {"id": widget.id, "dashboard_id": dashboard_id}


@router.delete("/dashboards/{dashboard_id}/widgets/{widget_id}")
async def remove_widget(dashboard_id: str, widget_id: str, db: AsyncSession = Depends(get_db)):
    widget = await db.get(DashboardWidget, widget_id)
    if not widget or widget.dashboard_id != dashboard_id:
        raise NotFound("Widget not found")
    await db.delete(widget)
    await db.commit()
    return {"deleted": widget_id}


@router.patch("/dashboards/{dashboard_id}/share")
async def share_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise NotFound("Dashboard not found")
    dashboard.is_shared = True
    dashboard.share_token = dashboard.share_token or secrets.token_urlsafe(24)
    await db.commit()
    return {"share_token": dashboard.share_token}


@router.delete("/dashboards/{dashboard_id}")
async def delete_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise NotFound("Dashboard not found")
    await db.delete(dashboard)
    await db.commit()
    return {"deleted": dashboard_id}


# ------------------------------------------------------------------ feedback
@router.post("/feedback")
async def submit_feedback(feedback_in: FeedbackIn, db: AsyncSession = Depends(get_db)):
    feedback = Feedback(**feedback_in.model_dump())
    db.add(feedback)
    if feedback_in.execution_id:
        await _library.apply_feedback(db, feedback_in.execution_id,
                                      positive=feedback_in.rating == "up")
    await audit(db, "default", "feedback.submit", detail={
        "rating": feedback_in.rating, "category": feedback_in.category,
    })
    await db.commit()
    return {"id": feedback.id}


@router.get("/feedback")
async def list_feedback(status: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Feedback).order_by(Feedback.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(Feedback.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {c: getattr(f, c) for c in (
            "id", "execution_id", "rating", "category", "comment",
            "corrected_sql", "status", "created_at",
        )}
        for f in rows
    ]


# ------------------------------------------------------------------ executions
@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    execution = await db.get(ExecutionHistory, execution_id)
    if not execution:
        raise NotFound("Execution not found")
    return {c: getattr(execution, c) for c in (
        "id", "prompt", "refined_prompt", "intent", "execution_plan", "generated_sql",
        "optimized_sql", "status", "row_count", "execution_time_ms", "cost_estimate",
        "confidence", "warnings", "error", "llm_model", "llm_provider", "token_usage",
        "tables_used", "created_at",
    )}
