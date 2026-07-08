"""Approval workflow, metadata versioning, and audit trail."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class ApprovalItem(Base, IdMixin, TimestampMixin):
    """Every AI-generated or imported metadata change waits here for review."""

    __tablename__ = "approval_items"

    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    # table_description | column_description | tag | glossary_term | synonym |
    # classification | relationship | metric
    entity_id: Mapped[str] = mapped_column(String(32), index=True)   # catalog/glossary row id
    entity_label: Mapped[str] = mapped_column(String(512))           # human-readable target name
    field: Mapped[str] = mapped_column(String(64))                   # which attribute changes
    current_value: Mapped[str | None] = mapped_column(Text)
    proposed_value: Mapped[str] = mapped_column(Text)
    proposed_payload: Mapped[dict | None] = mapped_column(JSON)      # structured proposals
    source: Mapped[str] = mapped_column(String(16), default="ai")    # ai | import | manual
    confidence: Mapped[float | None] = mapped_column(Float)
    rationale: Mapped[str | None] = mapped_column(Text)              # why the AI proposed it
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending | approved | rejected | edited
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    final_value: Mapped[str | None] = mapped_column(Text)            # value after optional edit


class MetadataVersion(Base, IdMixin, TimestampMixin):
    """Version history for rollback of any metadata attribute."""

    __tablename__ = "metadata_versions"

    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(32), index=True)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    changed_by: Mapped[str] = mapped_column(String(64), default="system")
    change_source: Mapped[str] = mapped_column(String(32), default="manual")
    approval_id: Mapped[str | None] = mapped_column(String(32))


class AuditLog(Base, IdMixin, TimestampMixin):
    """Append-only audit of every significant platform action."""

    __tablename__ = "audit_logs"

    user_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    # chat.query | sql.execute | guardrail.block | metadata.approve | admin.config_change | ...
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info|warning|critical
