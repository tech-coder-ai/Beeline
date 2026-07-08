"""Runtime-editable configuration stored in the repository (admin console).

File config (settings.yaml) provides defaults; rows here override at runtime.
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class ConfigOverride(Base, IdMixin, TimestampMixin):
    __tablename__ = "config_overrides"

    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # dot path
    value: Mapped[dict | None] = mapped_column(JSON)  # {"value": <any>}
    updated_by: Mapped[str] = mapped_column(String(64), default="admin")


class PromptTemplate(Base, IdMixin, TimestampMixin):
    __tablename__ = "prompt_templates"

    name: Mapped[str] = mapped_column(String(128), index=True)  # intent|planner|enrichment|...
    version: Mapped[int] = mapped_column(default=1)
    template: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class ApiAction(Base, IdMixin, TimestampMixin):
    """Configurable result-grid action buttons (Create Ticket, Trigger Workflow...)."""

    __tablename__ = "api_actions"

    action_id: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(128))
    icon: Mapped[str | None] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(8), default="POST")
    url: Mapped[str] = mapped_column(Text)
    headers: Mapped[dict | None] = mapped_column(JSON, default=dict)
    body_template: Mapped[str | None] = mapped_column(Text)  # {{placeholders}} from result context
    confirm: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
