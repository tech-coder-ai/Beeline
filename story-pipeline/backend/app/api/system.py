"""Assets, settings, health and the overview dashboard."""
from __future__ import annotations

import asyncio
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_or_404, settings_dep
from app.api.serializers import job_view
from app.config import Settings
from app.domain.states import STAGES
from app.media import ffmpeg_filters, have_ffmpeg
from app.persistence.models import Asset, Project, Publication, StorySource, WorkflowJob
from app.providers.registry import build_image, build_llm, build_publisher, build_tts
from app.services.assets import AssetStore

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/assets/{asset_id}/file")
def asset_file(asset_id: str, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    asset = get_or_404(db, Asset, asset_id)
    path = AssetStore(settings, asset.project_id).path_of(asset)
    if not path.exists():
        raise HTTPException(410, "asset file is missing on disk")
    return FileResponse(path, media_type=asset.mime_type, filename=path.name if asset.kind in ("video", "subtitles") else None)


@router.get("/assets/{asset_id}")
def asset_info(asset_id: str, db: Session = Depends(get_db)):
    a = get_or_404(db, Asset, asset_id)
    return {"id": a.id, "kind": a.kind, "rel_path": a.rel_path, "mime_type": a.mime_type, "checksum": a.checksum,
            "size_bytes": a.size_bytes, "provider": a.provider, "model": a.model, "prompt": a.prompt, "seed": a.seed,
            "meta": a.meta, "created_at": a.created_at}


@router.get("/settings")
def get_settings_view(settings: Settings = Depends(settings_dep)):
    d = settings.model_dump()
    d["models"]["llm"]["api_key"] = "***" if settings.models.llm.api_key else ""
    d["stages"] = [{"stage": s.stage.value, "label": s.label, "checkpoint": s.checkpoint} for s in STAGES]
    return d


@router.get("/health")
async def health(settings: Settings = Depends(settings_dep)):
    llm = build_llm(settings)
    image = build_image(settings)
    filters = ffmpeg_filters() if have_ffmpeg() else set()
    voices = []
    for code in settings.languages.all_codes():
        lang = settings.languages.languages[code]
        for v in [lang.narrator, *lang.character_pool]:
            h = build_tts(settings, v).health(v)
            voices.append({"language": code, "voice_id": v.voice_id, "provider": v.provider, "voice": v.voice, **h})
    pub = build_publisher(settings, settings.data_dir / "_health")
    return {
        "config_version": settings.config_version,
        "mode": settings.pipeline.mode,
        "llm": {"provider": llm.name, **(await llm.health())},
        "image": {"provider": image.name, **(await asyncio.to_thread(image.health))},
        "ffmpeg": {"ok": have_ffmpeg(), "detail": "zoompan/subtitles/loudnorm present"
                   if {"zoompan", "subtitles", "loudnorm"} <= filters else f"missing filters: {sorted({'zoompan', 'subtitles', 'loudnorm'} - filters)}"},
        "voices": voices,
        "publisher": {"provider": pub.name, **(await asyncio.to_thread(pub.health))},
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    projects = db.scalars(select(Project)).all()
    jobs = db.scalars(select(WorkflowJob).order_by(WorkflowJob.created_at.desc())).all()
    by_stage: dict[str, list[float]] = defaultdict(list)
    for j in jobs:
        if j.status == "SUCCEEDED" and j.started_at and j.finished_at:
            by_stage[j.stage].append((j.finished_at - j.started_at).total_seconds())
    disk = 0
    root = settings.data_dir / "projects"
    if root.exists():
        disk = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    return {
        "projects_by_status": dict(Counter(p.status for p in projects)),
        "awaiting_approval": [{"id": p.id, "name": p.name, "checkpoint": p.pending_checkpoint}
                              for p in projects if p.pending_checkpoint],
        "stories_by_rights": dict(db.execute(select(StorySource.rights_status, func.count()).group_by(StorySource.rights_status)).all()),
        "active_jobs": [job_view(j) for j in jobs if j.status in ("QUEUED", "RUNNING", "RETRY_PENDING")],
        "failed_jobs": [job_view(j) for j in jobs if j.status == "FAILED"][:10],
        "recent_jobs": [job_view(j) for j in jobs[:15]],
        "published": db.scalar(select(func.count()).select_from(Publication).where(Publication.status.in_(["uploaded", "processed"]))),
        # "Measure the actual time for each stage" - this is where bottlenecks show up.
        "stage_timings": {s: {"runs": len(v), "avg_seconds": round(sum(v) / len(v), 1), "max_seconds": round(max(v), 1)}
                          for s, v in by_stage.items()},
        "storage_bytes": disk,
    }
