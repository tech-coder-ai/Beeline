"""Projects: create, inspect, run stages, approve checkpoints, targeted regeneration."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_or_404, settings_dep, wake_runner
from app.api.serializers import job_view, project_detail, project_summary
from app.config import Settings
from app.domain.states import ProjectStatus, Stage, rank
from app.persistence.models import Character, Localization, Project, Scene, StorySource
from app.services.rights.service import RightsError, assert_usable
from app.workflow import engine
from app.workflow.engine import WorkflowError

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProject(BaseModel):
    source_id: str
    name: str | None = None
    production_style: Literal["illustrated_narration", "hybrid_animation"] = "illustrated_narration"


class PublishRequest(BaseModel):
    visibility: Literal["private", "unlisted", "public"] | None = None
    languages: list[str] | None = None


class Decision(BaseModel):
    note: str | None = None
    continue_pipeline: bool = True
    regenerate: list[str] | None = None


class SegmentEdit(BaseModel):
    text: str


def _load(db: Session, project_id: str) -> Project:
    return get_or_404(db, Project, project_id)


def _enqueue(request: Request, db: Session, settings: Settings, project: Project, stage: Stage,
             continue_pipeline: bool = False, options: dict | None = None) -> dict:
    try:
        job = engine.enqueue(db, settings, project, stage, continue_pipeline=continue_pipeline, options=options)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    wake_runner(request)
    return job_view(job)


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    return [project_summary(p, db) for p in db.scalars(select(Project).order_by(Project.created_at.desc()))]


@router.post("", status_code=201)
def create_project(body: CreateProject, request: Request, db: Session = Depends(get_db),
                   settings: Settings = Depends(settings_dep)):
    src = get_or_404(db, StorySource, body.source_id)
    try:
        assert_usable(src)  # the rights gate: no project from an unapproved source
    except RightsError as exc:
        raise HTTPException(422, str(exc)) from exc
    p = Project(name=body.name or src.title, source_id=src.id, production_style=body.production_style,
                status=ProjectStatus.SOURCE_APPROVED.value, config_version=settings.config_version,
                languages=settings.languages.all_codes())
    db.add(p)
    db.flush()
    return project_detail(p, db)


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    return project_detail(_load(db, project_id), db)


@router.post("/{project_id}/run")
def run_pipeline(project_id: str, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    """Run the next stage and keep going until a checkpoint, a failure or the end."""
    p = _load(db, project_id)
    try:
        job = engine.enqueue_next(db, settings, p)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    if job is None:
        raise HTTPException(409, f"nothing to run from status {p.status}"
                                 + (f" (approve '{p.pending_checkpoint}' first)" if p.pending_checkpoint else ""))
    db.commit()
    wake_runner(request)
    return job_view(job)


STAGE_ENDPOINTS = {
    "generate-script": Stage.SCRIPT, "generate-characters": Stage.CHARACTERS, "generate-scenes": Stage.SCENES,
    "localize": Stage.AUDIO, "render": Stage.RENDER, "qc": Stage.QC,
}


@router.post("/{project_id}/stages/{stage}")
def run_stage(project_id: str, stage: Stage, request: Request, db: Session = Depends(get_db),
              settings: Settings = Depends(settings_dep)):
    return _enqueue(request, db, settings, _load(db, project_id), stage)


def _make_stage_endpoint(stage: Stage):
    def endpoint(project_id: str, request: Request, db: Session = Depends(get_db),
                 settings: Settings = Depends(settings_dep)):
        return _enqueue(request, db, settings, _load(db, project_id), stage)
    endpoint.__name__ = f"run_{stage.value}"
    return endpoint


for _path, _stage in STAGE_ENDPOINTS.items():
    router.add_api_route(f"/{{project_id}}/{_path}", _make_stage_endpoint(_stage), methods=["POST"],
                         summary=f"Run the {_stage.value} stage")


@router.post("/{project_id}/publish")
def publish(project_id: str, request: Request, body: PublishRequest | None = None, db: Session = Depends(get_db),
            settings: Settings = Depends(settings_dep)):
    p = _load(db, project_id)
    if p.status not in (ProjectStatus.QC_APPROVED.value, ProjectStatus.UPLOADED.value):
        raise HTTPException(409, f"publishing requires an approved final render (project is {p.status})")
    opts = (body or PublishRequest()).model_dump(exclude_none=True)
    return _enqueue(request, db, settings, p, Stage.PUBLISH, options=opts)


@router.post("/{project_id}/checkpoints/{checkpoint}/approve")
def approve_checkpoint(project_id: str, checkpoint: str, request: Request, body: Decision | None = None,
                       db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    p = _load(db, project_id)
    b = body or Decision()
    try:
        job = engine.approve(db, settings, p, checkpoint, note=b.note, continue_pipeline=b.continue_pipeline)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    wake_runner(request)
    return {"project": project_summary(p, db), "job": job_view(job) if job else None}


@router.post("/{project_id}/checkpoints/{checkpoint}/reject")
def reject_checkpoint(project_id: str, checkpoint: str, body: Decision | None = None, db: Session = Depends(get_db)):
    p = _load(db, project_id)
    b = body or Decision()
    try:
        engine.reject(db, p, checkpoint, note=b.note, regenerate=b.regenerate)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    return project_summary(p, db)


def _regenerate(request: Request, db: Session, settings: Settings, p: Project, stage: Stage,
                what: str, back_to: ProjectStatus) -> dict:
    if engine.active_job(db, p.id):
        raise HTTPException(409, "a job is active for this project")
    if rank(p.status) < rank(back_to) or p.status == ProjectStatus.UPLOADED.value:
        raise HTTPException(409, f"cannot regenerate {what} from status {p.status}")
    engine.withdraw_checkpoint(db, p, f"regenerate {what}")
    if rank(p.status) > rank(back_to):
        p.status = back_to.value  # later stages will re-run; their caches keep unchanged work
    return _enqueue(request, db, settings, p, stage, continue_pipeline=False)


@router.post("/{project_id}/scenes/{scene_id}/regenerate")
def regenerate_scene(project_id: str, scene_id: str, request: Request, db: Session = Depends(get_db),
                     settings: Settings = Depends(settings_dep)):
    p = _load(db, project_id)
    sc = db.scalars(select(Scene).where(Scene.project_id == p.id, Scene.scene_id == scene_id)).first()
    if sc is None:
        raise HTTPException(404, "scene not found")
    sc.seed += 1  # new seed -> new fingerprint -> only this scene is redrawn
    return _regenerate(request, db, settings, p, Stage.SCENES, scene_id, ProjectStatus.CHARACTERS_READY)


@router.post("/{project_id}/characters/{character_id}/regenerate")
def regenerate_character(project_id: str, character_id: str, request: Request, db: Session = Depends(get_db),
                         settings: Settings = Depends(settings_dep)):
    p = _load(db, project_id)
    c = db.scalars(select(Character).where(Character.project_id == p.id, Character.character_id == character_id)).first()
    if c is None:
        raise HTTPException(404, "character not found")
    c.seed += 1
    return _regenerate(request, db, settings, p, Stage.CHARACTERS, character_id, ProjectStatus.SCRIPT_READY)


@router.patch("/{project_id}/localizations/{language}/segments/{segment_id}")
def edit_segment(project_id: str, language: str, segment_id: str, body: SegmentEdit, db: Session = Depends(get_db)):
    """Fix one translated line. The next audio run re-voices just this segment."""
    p = _load(db, project_id)
    loc = db.scalars(select(Localization).where(Localization.project_id == p.id, Localization.language == language)).first()
    if loc is None:
        raise HTTPException(404, "localization not found")
    segs = [dict(s) for s in loc.segments]
    for s in segs:
        if s["segment_id"] == segment_id:
            s["text"] = body.text.strip()
            break
    else:
        raise HTTPException(404, "segment not found")
    loc.segments = segs
    if rank(p.status) > rank(ProjectStatus.SCENES_READY) and not engine.active_job(db, p.id):
        engine.withdraw_checkpoint(db, p, f"edited {language}/{segment_id}")
        p.status = ProjectStatus.SCENES_READY.value
    return {"ok": True, "status": p.status}


@router.post("/{project_id}/cancel")
def cancel_project(project_id: str, db: Session = Depends(get_db)):
    p = _load(db, project_id)
    job = engine.active_job(db, p.id)
    if job:
        engine.cancel(db, job)
    p.status = ProjectStatus.CANCELLED.value
    p.pending_checkpoint = None
    return project_summary(p, db)
