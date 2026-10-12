"""ORM -> JSON views. Kept in one place so the UI contract is easy to see and change."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.states import STAGES, Stage, can_run, next_stage
from app.persistence.models import (
    Approval,
    AudioSegment,
    Character,
    Localization,
    Project,
    Publication,
    RenderJob,
    Scene,
    StorySource,
    StoryVersion,
    WorkflowJob,
)


def asset_url(asset_id: str | None) -> str | None:
    return f"/api/assets/{asset_id}/file" if asset_id else None


def source_view(s: StorySource, full: bool = False) -> dict[str, Any]:
    d = {
        "id": s.id, "connector": s.connector, "title": s.title, "author": s.author, "source_url": s.source_url,
        "published": s.published, "language": s.language, "category": s.category, "synopsis": s.synopsis,
        "word_count": s.word_count, "content_hash": s.content_hash[:16], "license_type": s.license_type,
        "suggested_license": s.suggested_license, "license_evidence_url": s.license_evidence_url,
        "license_notes": s.license_notes, "rights_status": s.rights_status, "allowed_uses": s.allowed_uses,
        "attribution": s.attribution, "rights_decided_by": s.rights_decided_by,
        "rights_decided_at": s.rights_decided_at, "retrieved_at": s.retrieved_at, "score": s.score,
        "score_breakdown": s.score_breakdown, "estimated_minutes": round(s.word_count / 150, 1),
    }
    if full:
        d["text"] = s.text
    return d


def job_view(j: WorkflowJob) -> dict[str, Any]:
    dur = (j.finished_at - j.started_at).total_seconds() if j.finished_at and j.started_at else None
    return {
        "id": j.id, "project_id": j.project_id, "stage": j.stage, "status": j.status, "attempts": j.attempts,
        "max_attempts": j.max_attempts, "progress": j.progress, "message": j.message, "error": j.error,
        "output": j.output, "continue_pipeline": j.continue_pipeline, "cancel_requested": j.cancel_requested,
        "config_version": j.config_version, "created_at": j.created_at, "started_at": j.started_at,
        "finished_at": j.finished_at, "duration_seconds": dur, "not_before": j.not_before,
    }


def project_summary(p: Project, db: Session) -> dict[str, Any]:
    last = db.scalars(select(WorkflowJob).where(WorkflowJob.project_id == p.id)
                      .order_by(WorkflowJob.created_at.desc())).first()
    return {
        "id": p.id, "name": p.name, "status": p.status, "pending_checkpoint": p.pending_checkpoint,
        "production_style": p.production_style, "source_id": p.source_id, "source_title": p.source.title,
        "languages": p.languages, "config_version": p.config_version, "created_at": p.created_at,
        "updated_at": p.updated_at, "last_job": job_view(last) if last else None,
    }


def project_detail(p: Project, db: Session) -> dict[str, Any]:
    d = project_summary(p, db)
    jobs = db.scalars(select(WorkflowJob).where(WorkflowJob.project_id == p.id)
                      .order_by(WorkflowJob.created_at.desc())).all()
    latest_by_stage: dict[str, WorkflowJob] = {}
    for j in jobs:
        latest_by_stage.setdefault(j.stage, j)
    nxt = next_stage(p.status)
    d["stages"] = [{
        "stage": spec.stage.value, "label": spec.label, "requires": spec.requires.value,
        "produces": spec.produces.value, "checkpoint": spec.checkpoint,
        "can_run": can_run(spec.stage, p.status) and not p.pending_checkpoint,
        "is_next": nxt is not None and nxt.stage == spec.stage,
        "latest_job": job_view(latest_by_stage[spec.stage.value]) if spec.stage.value in latest_by_stage else None,
    } for spec in STAGES]
    d["jobs"] = [job_view(j) for j in jobs[:30]]
    d["source"] = source_view(p.source)

    sv = db.get(StoryVersion, p.current_story_version_id) if p.current_story_version_id else None
    d["story"] = None if sv is None else {
        "id": sv.id, "version": sv.version, "bible": sv.bible, "script": sv.script, "issues": sv.issues,
        "generated_by": sv.generated_by, "approved": sv.approved, "created_at": sv.created_at,
    }
    d["characters"] = [{
        "id": c.id, "character_id": c.character_id, "name": c.name, "profile": c.profile, "seed": c.seed,
        "approved": c.approved, "reference_url": asset_url(c.reference_asset_id),
    } for c in db.scalars(select(Character).where(Character.project_id == p.id).order_by(Character.character_id))]
    d["scenes"] = [{
        "id": s.id, "scene_id": s.scene_id, "sequence": s.sequence, "spec": s.spec, "seed": s.seed,
        "status": s.status, "error": s.error, "image_url": asset_url(s.image_asset_id),
    } for s in db.scalars(select(Scene).where(Scene.project_id == p.id).order_by(Scene.sequence))]
    audio: dict[str, list[dict]] = {}
    for a in db.scalars(select(AudioSegment).where(AudioSegment.project_id == p.id).order_by(AudioSegment.order)):
        audio.setdefault(a.language, []).append({
            "segment_id": a.segment_id, "scene_id": a.scene_id, "speaker": a.speaker, "text": a.text,
            "voice_id": a.voice_id, "tts_provider": a.tts_provider, "duration": round(a.duration_seconds, 2),
            "status": a.status, "note": a.note, "audio_url": asset_url(a.asset_id)})
    d["localizations"] = [{
        "language": l.language, "status": l.status, "generated_by": l.generated_by, "note": l.note,
        "segments": l.segments, "glossary": l.glossary, "audio": audio.get(l.language, []),
    } for l in db.scalars(select(Localization).where(Localization.project_id == p.id))]
    d["renders"] = [{
        "id": r.id, "language": r.language, "status": r.status, "duration": r.timeline.get("duration"),
        "video_url": asset_url(r.video_asset_id), "subtitles_url": asset_url(r.subtitle_asset_id),
        "thumbnail_url": asset_url(r.thumbnail_asset_id), "metadata": r.metadata_, "qc": r.qc,
        "qc_passed": r.qc_passed, "render_seconds": r.render_seconds, "updated_at": r.updated_at,
        "scene_times": [{"scene_id": s["scene_id"], "start": s["start"], "end": s["end"]}
                        for s in r.timeline.get("scenes", [])],
    } for r in db.scalars(select(RenderJob).where(RenderJob.project_id == p.id))]
    d["publications"] = [{
        "id": x.id, "language": x.language, "attempt_id": x.attempt_id, "provider": x.provider,
        "video_id": x.video_id, "url": x.url, "visibility": x.visibility, "status": x.status,
        "processing_status": x.processing_status, "retries": x.retries, "last_error": x.last_error,
        "confirmed_at": x.confirmed_at, "title": x.metadata_.get("title"),
    } for x in db.scalars(select(Publication).where(Publication.project_id == p.id).order_by(Publication.created_at))]
    d["approvals"] = [{
        "id": a.id, "checkpoint": a.checkpoint, "decision": a.decision, "decided_by": a.decided_by,
        "note": a.note, "created_at": a.created_at,
    } for a in db.scalars(select(Approval).where(Approval.project_id == p.id).order_by(Approval.created_at.desc()))]
    d["can_publish"] = can_run(Stage.PUBLISH, p.status) and not p.pending_checkpoint
    return d
