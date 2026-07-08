"""Semantic layer: business glossary, synonyms, metrics, KPIs."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class GlossaryTerm(Base, IdMixin, TimestampMixin):
    __tablename__ = "glossary_terms"

    term: Mapped[str] = mapped_column(String(255), index=True, unique=True)
    definition: Mapped[str] = mapped_column(Text)
    business_meaning: Mapped[str | None] = mapped_column(Text)
    examples: Mapped[list | None] = mapped_column(JSON, default=list)
    owner: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="approved")  # draft|approved
    source: Mapped[str] = mapped_column(String(16), default="manual")    # manual|ai|imported

    synonyms: Mapped[list["Synonym"]] = relationship(
        back_populates="term_ref", cascade="all, delete-orphan"
    )


class Synonym(Base, IdMixin, TimestampMixin):
    """Client = Customer, Sales = Revenue - resolved automatically in the pipeline."""

    __tablename__ = "synonyms"

    term_id: Mapped[str] = mapped_column(ForeignKey("glossary_terms.id"), index=True)
    synonym: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual|ai|learned
    confidence: Mapped[float | None] = mapped_column(Float)

    term_ref: Mapped[GlossaryTerm] = relationship(back_populates="synonyms")


class BusinessMetric(Base, IdMixin, TimestampMixin):
    """Named metric with its SQL expression, e.g. Revenue = SUM(order_amount)."""

    __tablename__ = "business_metrics"

    name: Mapped[str] = mapped_column(String(255), index=True, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    expression: Mapped[str] = mapped_column(Text)               # SQL expression
    table_qualified_name: Mapped[str | None] = mapped_column(String(512))
    unit: Mapped[str | None] = mapped_column(String(32))        # currency|percent|count|...
    aggregation: Mapped[str | None] = mapped_column(String(32))  # sum|avg|count|...
    is_kpi: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="approved")
