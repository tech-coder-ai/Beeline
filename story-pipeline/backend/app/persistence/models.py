"""SQLAlchemy models - the core entities from the implementation plan.

Conventions:
- Structured artifacts (story bible, scene spec, QC report) are stored as JSON
  columns validated by Pydantic schemas at the boundary.
- Files are never referenced by path from business tables; they reference an
  Asset row, and the Asset row owns the path + checksum (single asset registry).
- `fingerprint` columns hold a hash of every input that affects an output.
  If the inputs haven't changed, the stage reuses the output instead of
  regenerating it - this is what makes reruns cheap and resumable.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.db import Base


def _id(prefix: str):
    return lambda: f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StorySource(TimestampMixin, Base):
    """A candidate story plus its provenance and rights decision."""
    __tablename__ = "story_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("src"))
    connector: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(300))
    author: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    published: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="en")
    category: Mapped[str] = mapped_column(String(64), default="public_domain_archive")
    text: Mapped[str] = mapped_column(Text)
    synopsis: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # rights / provenance
    license_type: Mapped[str] = mapped_column(String(64), default="unknown")
    license_evidence_url: Mapped[str | None] = mapped_column(String(1000))
    license_notes: Mapped[str | None] = mapped_column(Text)
    suggested_license: Mapped[str | None] = mapped_column(String(64))  # what the connector claimed
    rights_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|approved|rejected|review_required
    allowed_uses: Mapped[list[str]] = mapped_column(JSON, default=list)       # adaptation, verbatim, commercial, attribution_required
    attribution: Mapped[str | None] = mapped_column(Text)
    rights_decided_by: Mapped[str | None] = mapped_column(String(64))
    rights_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    score: Mapped[float] = mapped_column(Float, default=0)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("prj"))
    name: Mapped[str] = mapped_column(String(200))
    source_id: Mapped[str] = mapped_column(ForeignKey("story_sources.id"))
    production_style: Mapped[str] = mapped_column(String(32), default="illustrated_narration")
    status: Mapped[str] = mapped_column(String(32), default="CREATED")
    pending_checkpoint: Mapped[str | None] = mapped_column(String(64))
    config_version: Mapped[str] = mapped_column(String(32))
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    current_story_version_id: Mapped[str | None] = mapped_column(String(32))

    source: Mapped[StorySource] = relationship()


class StoryVersion(TimestampMixin, Base):
    """Immutable output of one script-stage run. A rerun creates a new version."""
    __tablename__ = "story_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("sv"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    bible: Mapped[dict[str, Any]] = mapped_column(JSON)
    script: Mapped[dict[str, Any]] = mapped_column(JSON)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(64))   # e.g. "ollama:llama3.1:8b" or "heuristic"
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class Character(TimestampMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("project_id", "character_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("chr"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    character_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    profile: Mapped[dict[str, Any]] = mapped_column(JSON)
    seed: Mapped[int] = mapped_column(Integer)
    reference_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class Scene(TimestampMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("project_id", "scene_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("scn"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    scene_id: Mapped[str] = mapped_column(String(32))
    sequence: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    seed: Mapped[int] = mapped_column(Integer)
    image_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|generated|failed|approved
    error: Mapped[str | None] = mapped_column(Text)


class Asset(TimestampMixin, Base):
    """The single registry of every file the pipeline produces."""
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("ast"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))     # character_sheet|scene_image|audio_segment|subtitles|video|thumbnail|timeline|metadata
    rel_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(64))
    checksum: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Localization(TimestampMixin, Base):
    __tablename__ = "localizations"
    __table_args__ = (UniqueConstraint("project_id", "language"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("loc"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32))     # ready|skipped|failed
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    glossary: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    generated_by: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)


class AudioSegment(TimestampMixin, Base):
    __tablename__ = "audio_segments"
    __table_args__ = (UniqueConstraint("project_id", "language", "segment_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("aud"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    scene_id: Mapped[str] = mapped_column(String(32))
    segment_id: Mapped[str] = mapped_column(String(48))
    order: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    voice_id: Mapped[str] = mapped_column(String(64))
    tts_provider: Mapped[str] = mapped_column(String(32))
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    sample_rate: Mapped[int] = mapped_column(Integer, default=0)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")  # ok|fallback|failed
    note: Mapped[str | None] = mapped_column(Text)


class RenderJob(TimestampMixin, Base):
    __tablename__ = "render_jobs"
    __table_args__ = (UniqueConstraint("project_id", "language"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("rnd"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    timeline: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    video_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    subtitle_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    thumbnail_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")  # rendered|failed
    qc: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    qc_passed: Mapped[bool | None] = mapped_column(Boolean)
    render_seconds: Mapped[float] = mapped_column(Float, default=0)


class WorkflowJob(TimestampMixin, Base):
    """One attempt-tracked execution of one stage for one project."""
    __tablename__ = "workflow_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("job"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    continue_pipeline: Mapped[bool] = mapped_column(Boolean, default=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    config_version: Mapped[str] = mapped_column(String(32))
    progress: Mapped[float] = mapped_column(Float, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("apr"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    checkpoint: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))   # approved|rejected|auto
    decided_by: Mapped[str] = mapped_column(String(64), default="user")
    note: Mapped[str | None] = mapped_column(Text)
    story_version_id: Mapped[str | None] = mapped_column(String(32))


class Publication(TimestampMixin, Base):
    __tablename__ = "publications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id("pub"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    render_job_id: Mapped[str] = mapped_column(ForeignKey("render_jobs.id"))
    attempt_id: Mapped[str] = mapped_column(String(64), unique=True)
    provider: Mapped[str] = mapped_column(String(32))
    video_id: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(300))
    visibility: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|uploading|uploaded|processing|processed|failed
    processing_status: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
