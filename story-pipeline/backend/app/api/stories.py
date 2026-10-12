"""Story library: discovery, upload, rights review."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_or_404, settings_dep
from app.api.serializers import source_view
from app.config import Settings
from app.persistence.models import StorySource
from app.services.discovery.connectors import Candidate
from app.services.discovery.pipeline import connectors, discover, ingest
from app.services.rights.service import LICENSE_PRESETS, RightsError, decide

router = APIRouter(prefix="/api/stories", tags=["stories"])


class DiscoverRequest(BaseModel):
    connector: str = "library"
    query: str = ""
    limit: int = Field(10, ge=1, le=50)


class UploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str | None = None
    text: str = Field(min_length=50)
    source_url: str | None = None
    license_type: str | None = "user_owned"
    license_notes: str | None = None
    attribution: str | None = None


class RightsRequest(BaseModel):
    status: Literal["pending", "approved", "rejected", "review_required"]
    license_type: str | None = None
    allowed_uses: list[str] | None = None
    evidence_url: str | None = None
    notes: str | None = None
    attribution: str | None = None


@router.get("")
def list_stories(rights_status: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    stmt = select(StorySource).order_by(StorySource.score.desc(), StorySource.created_at.desc())
    if rights_status:
        stmt = stmt.where(StorySource.rights_status == rights_status)
    rows = db.scalars(stmt).all()
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r.title.lower() or ql in (r.author or "").lower()]
    return [source_view(r) for r in rows]


@router.get("/connectors")
def list_connectors(settings: Settings = Depends(settings_dep)):
    return {"connectors": sorted(connectors(settings)), "license_presets": LICENSE_PRESETS}


@router.post("/discover")
def discover_stories(body: DiscoverRequest, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    try:
        results = discover(db, settings, body.connector, body.query, body.limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # network etc.
        raise HTTPException(502, f"discovery failed: {exc}") from exc
    return [{"status": r.status, "detail": r.detail, "story": source_view(r.source) if r.source else None}
            for r in results]


@router.post("/upload")
def upload_story(body: UploadRequest, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    cand = Candidate(connector="upload", title=body.title, author=body.author, source_url=body.source_url,
                     category="user_upload", text=body.text, suggested_license=body.license_type,
                     license_notes=body.license_notes or "Uploaded by user; rights claimed by uploader.",
                     attribution=body.attribution)
    r = ingest(db, settings, cand)
    if r.source is None:
        raise HTTPException(400, r.detail)
    return {"status": r.status, "detail": r.detail, "story": source_view(r.source)}


@router.get("/{story_id}")
def get_story(story_id: str, db: Session = Depends(get_db)):
    return source_view(get_or_404(db, StorySource, story_id), full=True)


@router.post("/{story_id}/rights")
def set_rights(story_id: str, body: RightsRequest, db: Session = Depends(get_db)):
    src = get_or_404(db, StorySource, story_id)
    try:
        decide(src, status=body.status, license_type=body.license_type, allowed_uses=body.allowed_uses,
               evidence_url=body.evidence_url, notes=body.notes, attribution=body.attribution)
    except RightsError as exc:
        raise HTTPException(422, str(exc)) from exc
    return source_view(src, full=True)


@router.post("/{story_id}/approve")
def approve_story(story_id: str, body: RightsRequest | None = None, db: Session = Depends(get_db)):
    """Shortcut: approve using the suggested license unless the body overrides it."""
    src = get_or_404(db, StorySource, story_id)
    b = body or RightsRequest(status="approved")
    try:
        decide(src, status="approved", license_type=b.license_type or src.suggested_license,
               allowed_uses=b.allowed_uses, evidence_url=b.evidence_url, notes=b.notes, attribution=b.attribution)
    except RightsError as exc:
        raise HTTPException(422, str(exc)) from exc
    return source_view(src, full=True)
