"""Saved queries and the SQL knowledge library."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class SavedQuery(Base, IdMixin, TimestampMixin):
    """Explicitly saved by a user from the grid actions."""

    __tablename__ = "saved_queries"

    user_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    sql: Mapped[str] = mapped_column(Text)
    connector_id: Mapped[str | None] = mapped_column(String(64))
    prompt: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    is_bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_count: Mapped[int] = mapped_column(Integer, default=0)


class QueryLibraryEntry(Base, IdMixin, TimestampMixin):
    """Automatically captured successful queries, reused via semantic search
    before any new SQL generation ("SQL Knowledge Library")."""

    __tablename__ = "query_library"

    question: Mapped[str] = mapped_column(Text, index=True)
    normalized_question: Mapped[str] = mapped_column(Text)      # lowercased, synonym-resolved
    sql: Mapped[str] = mapped_column(Text)
    connector_id: Mapped[str | None] = mapped_column(String(64))
    tables_used: Mapped[list | None] = mapped_column(JSON, default=list)
    intent: Mapped[dict | None] = mapped_column(JSON)
    execution_plan: Mapped[dict | None] = mapped_column(JSON)
    success_count: Mapped[int] = mapped_column(Integer, default=1)
    positive_feedback: Mapped[int] = mapped_column(Integer, default=0)
    negative_feedback: Mapped[int] = mapped_column(Integer, default=0)
    avg_execution_ms: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # disabled on repeated 👎
