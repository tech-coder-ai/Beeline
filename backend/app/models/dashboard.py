"""Dashboards composed of pinned chat results, charts, cards, and grids."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Dashboard(Base, IdMixin, TimestampMixin):
    __tablename__ = "dashboards"

    user_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    refresh_interval_seconds: Mapped[int | None] = mapped_column(Integer)  # null = manual
    layout: Mapped[dict | None] = mapped_column(JSON)  # grid layout positions

    widgets: Mapped[list["DashboardWidget"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan", order_by="DashboardWidget.position"
    )


class DashboardWidget(Base, IdMixin, TimestampMixin):
    __tablename__ = "dashboard_widgets"

    dashboard_id: Mapped[str] = mapped_column(ForeignKey("dashboards.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    widget_type: Mapped[str] = mapped_column(String(32))  # kpi|chart|grid|text
    position: Mapped[int] = mapped_column(Integer, default=0)
    size: Mapped[str] = mapped_column(String(16), default="half")  # third|half|full
    sql: Mapped[str | None] = mapped_column(Text)                # re-runnable query
    connector_id: Mapped[str | None] = mapped_column(String(64))
    visualization: Mapped[dict | None] = mapped_column(JSON)     # renderer config (chart type etc.)
    snapshot: Mapped[dict | None] = mapped_column(JSON)          # last result snapshot
    source_execution_id: Mapped[str | None] = mapped_column(String(32))

    dashboard: Mapped[Dashboard] = relationship(back_populates="widgets")
