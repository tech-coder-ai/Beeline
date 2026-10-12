from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_or_404, settings_dep, wake_runner
from app.api.serializers import job_view
from app.config import Settings
from app.persistence.models import WorkflowJob
from app.workflow import engine
from app.workflow.engine import WorkflowError

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(project_id: str | None = None, status: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    stmt = select(WorkflowJob).order_by(WorkflowJob.created_at.desc()).limit(min(limit, 500))
    if project_id:
        stmt = stmt.where(WorkflowJob.project_id == project_id)
    if status:
        stmt = stmt.where(WorkflowJob.status == status)
    return [job_view(j) for j in db.scalars(stmt)]


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return job_view(get_or_404(db, WorkflowJob, job_id))


@router.post("/{job_id}/retry")
def retry_job(job_id: str, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    job = get_or_404(db, WorkflowJob, job_id)
    try:
        engine.retry(db, job, settings.pipeline.max_attempts)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    wake_runner(request)
    return job_view(job)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = get_or_404(db, WorkflowJob, job_id)
    try:
        engine.cancel(db, job)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    return job_view(job)
