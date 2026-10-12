"""The workflow engine: queue stages, run them, record attempts, raise checkpoints.

Design rules:
- The database IS the queue. A job row is created QUEUED; the runner picks it
  up. If the process dies mid-stage, the row is still there (RUNNING) and is
  re-queued on restart. No broker needed for a single workstation.
- A stage handler is plain code that may call AI providers. The engine never
  calls a model itself - it only orchestrates.
- Retry policy lives here, not in each stage: transient provider errors are
  retried with backoff up to max_attempts; deterministic failures stop.
- Items inside a stage (scenes, segments...) are cached by fingerprint, so a
  retry resumes where the last attempt stopped.
"""
from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.states import (
    ACTIVE_JOB_STATUSES,
    SPEC_BY_CHECKPOINT,
    SPEC_BY_STAGE,
    JobStatus,
    ProjectStatus,
    Stage,
    can_run,
    next_stage,
)
from app.persistence.db import session_scope
from app.persistence.models import Approval, Character, Project, Scene, StoryVersion, WorkflowJob
from app.providers.errors import ProviderError
from app.services.assets import AssetStore
from app.services.rights.service import RightsError
from app.workflow.context import Cancelled, StageContext, StageFailed

log = logging.getLogger("workflow")

StageHandler = Callable[[StageContext], dict[str, Any]]


class WorkflowError(Exception):
    """Invalid request (wrong state, job already running...). Maps to HTTP 409."""


def _handlers() -> dict[Stage, StageHandler]:
    from app.services.animation.service import run_animate_stage
    from app.services.audio.service import run_audio_stage
    from app.services.characters.service import run_characters_stage
    from app.services.publishing.service import run_publish_stage
    from app.services.quality.qc import run_qc_stage
    from app.services.rendering.service import run_render_stage
    from app.services.scenes.service import run_scenes_stage
    from app.services.story.adaptation import run_script_stage

    return {
        Stage.SCRIPT: run_script_stage,
        Stage.CHARACTERS: run_characters_stage,
        Stage.SCENES: run_scenes_stage,
        Stage.ANIMATE: run_animate_stage,
        Stage.AUDIO: run_audio_stage,
        Stage.RENDER: run_render_stage,
        Stage.QC: run_qc_stage,
        Stage.PUBLISH: run_publish_stage,
    }


def checkpoint_required(settings: Settings, checkpoint: str) -> bool:
    if checkpoint == "final_render" and settings.publishing.require_approval:
        return True
    return settings.pipeline.mode == "approval_required" and checkpoint in settings.pipeline.checkpoint_after


# --------------------------------------------------------------------- enqueue
def active_job(db: Session, project_id: str) -> WorkflowJob | None:
    return db.scalars(
        select(WorkflowJob).where(WorkflowJob.project_id == project_id,
                                  WorkflowJob.status.in_([s.value for s in ACTIVE_JOB_STATUSES]))
    ).first()


def enqueue(db: Session, settings: Settings, project: Project, stage: Stage, *,
            continue_pipeline: bool = False, options: dict | None = None) -> WorkflowJob:
    if project.status == ProjectStatus.CANCELLED:
        raise WorkflowError("project is cancelled")
    if active_job(db, project.id):
        raise WorkflowError("a job is already queued or running for this project")
    if project.pending_checkpoint:
        raise WorkflowError(f"waiting for approval at checkpoint '{project.pending_checkpoint}'")
    if not can_run(stage, project.status):
        spec = SPEC_BY_STAGE[stage]
        need = "QC_APPROVED" if stage is Stage.PUBLISH else spec.requires.value
        raise WorkflowError(f"stage '{stage.value}' needs status {need}; project is {project.status}")
    job = WorkflowJob(project_id=project.id, stage=stage.value, status=JobStatus.QUEUED.value,
                      max_attempts=settings.pipeline.max_attempts, continue_pipeline=continue_pipeline,
                      options=options or {}, config_version=settings.config_version)
    db.add(job)
    db.flush()
    return job


def enqueue_next(db: Session, settings: Settings, project: Project) -> WorkflowJob | None:
    spec = next_stage(project.status)
    if spec is None:
        return None
    return enqueue(db, settings, project, spec.stage, continue_pipeline=True)


# ------------------------------------------------------------------- approvals
def approve(db: Session, settings: Settings, project: Project, checkpoint: str, *, note: str | None = None,
            continue_pipeline: bool = True, decided_by: str = "user") -> WorkflowJob | None:
    if project.pending_checkpoint != checkpoint:
        raise WorkflowError(f"project is not waiting at '{checkpoint}' (pending: {project.pending_checkpoint})")
    _record_approval(db, project, checkpoint, "approved", note, decided_by)
    _apply_approval(db, project, checkpoint)
    project.pending_checkpoint = None
    db.flush()
    if checkpoint == "final_render" and settings.pipeline.mode == "approval_required":
        # Approving the final cut does not upload it: publishing (and its visibility) is a separate,
        # deliberate action in approval mode. Fully automated mode carries straight on.
        return None
    return enqueue_next(db, settings, project) if continue_pipeline else None


def reject(db: Session, project: Project, checkpoint: str, *, note: str | None = None,
           regenerate: list[str] | None = None) -> None:
    """Send the project back to the start of the stage that raised the checkpoint.

    For visual checkpoints the listed items (or all, if none listed) get a new seed,
    which changes their fingerprint, so the next run regenerates exactly those.
    """
    if project.pending_checkpoint != checkpoint:
        raise WorkflowError(f"project is not waiting at '{checkpoint}'")
    spec = SPEC_BY_CHECKPOINT[checkpoint]
    _record_approval(db, project, checkpoint, "rejected", note, "user")
    if checkpoint == "character_generation":
        for c in db.scalars(select(Character).where(Character.project_id == project.id)):
            if not regenerate or c.character_id in regenerate:
                c.seed += 1
    elif checkpoint == "scene_generation":
        for sc in db.scalars(select(Scene).where(Scene.project_id == project.id)):
            if not regenerate or sc.scene_id in regenerate:
                sc.seed += 1
    project.pending_checkpoint = None
    project.status = spec.requires.value
    db.flush()


def withdraw_checkpoint(db: Session, project: Project, note: str) -> None:
    """Leave a pending checkpoint because the user chose to rework something (recorded as a rejection)."""
    if project.pending_checkpoint:
        _record_approval(db, project, project.pending_checkpoint, "rejected", note, "user")
        project.pending_checkpoint = None


def _record_approval(db: Session, project: Project, checkpoint: str, decision: str, note: str | None,
                     decided_by: str) -> None:
    db.add(Approval(project_id=project.id, checkpoint=checkpoint, decision=decision, note=note,
                    decided_by=decided_by, story_version_id=project.current_story_version_id))


def _apply_approval(db: Session, project: Project, checkpoint: str) -> None:
    if checkpoint == "story_adaptation" and project.current_story_version_id:
        sv = db.get(StoryVersion, project.current_story_version_id)
        if sv:
            sv.approved = True
    elif checkpoint == "character_generation":
        for c in db.scalars(select(Character).where(Character.project_id == project.id)):
            c.approved = True
    elif checkpoint == "scene_generation":
        for sc in db.scalars(select(Scene).where(Scene.project_id == project.id)):
            sc.status = "approved"
    elif checkpoint == "final_render":
        project.status = ProjectStatus.QC_APPROVED.value


# ------------------------------------------------------------------- execution
def run_job(job_id: str, settings: Settings, handlers: dict[Stage, StageHandler] | None = None) -> str:
    """Execute one job. Returns the final job status. Never raises for stage failures."""
    handlers = handlers or _handlers()
    with session_scope() as db:
        job = db.get(WorkflowJob, job_id)
        if job is None or job.status not in (JobStatus.QUEUED.value, JobStatus.RETRY_PENDING.value):
            return job.status if job else "MISSING"
        if job.cancel_requested:
            job.status = JobStatus.CANCELLED.value
            job.finished_at = datetime.now(UTC)
            return job.status
        job.status = JobStatus.RUNNING.value
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        job.error = None
        stage = Stage(job.stage)
        project_id, options = job.project_id, dict(job.options or {})

    ctx = StageContext(settings=settings, project_id=project_id, job_id=job_id, options=options,
                       session_factory=session_scope, assets=AssetStore(settings, project_id))
    log.info("job %s: %s for %s (attempt starts)", job_id, stage.value, project_id)
    try:
        output = handlers[stage](ctx) or {}
    except Cancelled:
        return _finish(job_id, JobStatus.CANCELLED, message="cancelled by user")
    except ProviderError as exc:
        return _fail(job_id, settings, str(exc), transient=exc.transient)
    except (StageFailed, RightsError) as exc:
        return _fail(job_id, settings, str(exc), transient=False)
    except Exception as exc:  # noqa: BLE001 - unexpected bug: record it, don't kill the runner
        log.exception("job %s crashed", job_id)
        return _fail(job_id, settings, f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=6)}",
                     transient=False)

    if ctx.warnings:
        output["warnings"] = ctx.warnings
    with session_scope() as db:
        job = db.get(WorkflowJob, job_id)
        project = db.get(Project, project_id)
        spec = SPEC_BY_STAGE[stage]
        project.status = spec.produces.value
        if spec.checkpoint:
            if checkpoint_required(settings, spec.checkpoint):
                project.pending_checkpoint = spec.checkpoint
            else:
                _record_approval(db, project, spec.checkpoint, "auto", "checkpoint disabled by config", "system")
                _apply_approval(db, project, spec.checkpoint)
        job.status = JobStatus.SUCCEEDED.value
        job.progress = 1.0
        job.message = "awaiting approval" if project.pending_checkpoint else "done"
        job.output = output
        job.finished_at = datetime.now(UTC)
        db.flush()
        if job.continue_pipeline and not project.pending_checkpoint:
            try:
                enqueue_next(db, settings, project)
            except WorkflowError as exc:
                log.info("pipeline stops for %s: %s", project_id, exc)
    return JobStatus.SUCCEEDED.value


def _finish(job_id: str, status: JobStatus, message: str) -> str:
    with session_scope() as db:
        job = db.get(WorkflowJob, job_id)
        job.status = status.value
        job.message = message
        job.finished_at = datetime.now(UTC)
    return status.value


def _fail(job_id: str, settings: Settings, error: str, *, transient: bool) -> str:
    with session_scope() as db:
        job = db.get(WorkflowJob, job_id)
        job.error = error[:8000]
        if transient and job.attempts < job.max_attempts:
            delay = settings.pipeline.retry_backoff_seconds * (2 ** (job.attempts - 1))
            job.status = JobStatus.RETRY_PENDING.value
            job.not_before = datetime.now(UTC) + timedelta(seconds=delay)
            job.message = f"transient failure; retry {job.attempts + 1}/{job.max_attempts} in {delay:.0f}s"
        else:
            job.status = JobStatus.FAILED.value
            job.message = "failed - fix the cause and press Retry" if not transient else "gave up after retries"
            job.finished_at = datetime.now(UTC)
        log.warning("job %s %s: %s", job_id, job.status, error.splitlines()[0] if error else "")
        return job.status


def retry(db: Session, job: WorkflowJob, max_attempts: int = 3) -> WorkflowJob:
    """Manual retry of a failed/cancelled job: same stage, fresh attempt budget, cached items reused."""
    if job.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        raise WorkflowError(f"only FAILED or CANCELLED jobs can be retried (job is {job.status})")
    if active_job(db, job.project_id):
        raise WorkflowError("another job is active for this project")
    job.status = JobStatus.QUEUED.value
    job.max_attempts = job.attempts + max_attempts  # a fresh automatic-retry budget
    job.cancel_requested = False
    job.not_before = None
    job.finished_at = None
    job.message = "queued for retry"
    return job


def cancel(db: Session, job: WorkflowJob) -> WorkflowJob:
    if job.status in (JobStatus.QUEUED.value, JobStatus.RETRY_PENDING.value):
        job.status = JobStatus.CANCELLED.value
        job.finished_at = datetime.now(UTC)
        job.message = "cancelled before start"
    elif job.status == JobStatus.RUNNING.value:
        job.cancel_requested = True  # the stage stops at its next item boundary
        job.message = "cancellation requested"
    else:
        raise WorkflowError(f"job is already {job.status}")
    return job


def recover_interrupted(db: Session) -> int:
    """On startup: jobs left RUNNING by a crash are re-queued (cached items make this cheap)."""
    n = 0
    for job in db.scalars(select(WorkflowJob).where(WorkflowJob.status == JobStatus.RUNNING.value)):
        job.status = JobStatus.RETRY_PENDING.value
        job.not_before = None
        job.message = "interrupted by restart; resuming"
        n += 1
    return n
