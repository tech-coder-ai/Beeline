"""Synchronized analytics catalog: databases, tables, columns, relationships.

This is Beeline's copy of the analytics source metadata (harvested from Hive),
enriched with business context. The NL pipeline reads from these tables, never
from the live metastore.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class CatalogDatabase(Base, IdMixin, TimestampMixin):
    __tablename__ = "catalog_databases"

    connector_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tables: Mapped[list["CatalogTable"]] = relationship(
        back_populates="database", cascade="all, delete-orphan"
    )


class CatalogTable(Base, IdMixin, TimestampMixin):
    __tablename__ = "catalog_tables"

    database_id: Mapped[str] = mapped_column(ForeignKey("catalog_databases.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    table_type: Mapped[str] = mapped_column(String(32), default="TABLE")  # TABLE | VIEW
    description: Mapped[str | None] = mapped_column(Text)            # approved business description
    technical_comment: Mapped[str | None] = mapped_column(Text)      # comment from Hive
    owner: Mapped[str | None] = mapped_column(String(255))
    steward: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    classification: Mapped[str | None] = mapped_column(String(64))   # public|internal|confidential|pii
    row_count: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_format: Mapped[str | None] = mapped_column(String(64))
    compression: Mapped[str | None] = mapped_column(String(64))
    partition_columns: Mapped[list | None] = mapped_column(JSON, default=list)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usage_count: Mapped[int] = mapped_column(Integer, default=0)     # popularity for ranking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)   # false when dropped upstream

    database: Mapped[CatalogDatabase] = relationship(back_populates="tables")
    columns: Mapped[list["CatalogColumn"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="CatalogColumn.position"
    )

    @property
    def qualified_name(self) -> str:
        return f"{self.database.name}.{self.name}" if self.database else self.name


class CatalogColumn(Base, IdMixin, TimestampMixin):
    __tablename__ = "catalog_columns"

    table_id: Mapped[str] = mapped_column(ForeignKey("catalog_tables.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    data_type: Mapped[str] = mapped_column(String(128))
    inferred_semantic_type: Mapped[str | None] = mapped_column(String(64))  # currency|email|country|...
    semantic_confidence: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    technical_comment: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    classification: Mapped[str | None] = mapped_column(String(64))
    is_pii: Mapped[bool] = mapped_column(Boolean, default=False)
    is_partition: Mapped[bool] = mapped_column(Boolean, default=False)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, default=False)
    null_percentage: Mapped[float | None] = mapped_column(Float)
    distinct_percentage: Mapped[float | None] = mapped_column(Float)
    distinct_count: Mapped[int | None] = mapped_column(Integer)
    min_value: Mapped[str | None] = mapped_column(String(255))
    max_value: Mapped[str | None] = mapped_column(String(255))
    sample_values: Mapped[list | None] = mapped_column(JSON, default=list)
    top_values: Mapped[list | None] = mapped_column(JSON, default=list)

    table: Mapped[CatalogTable] = relationship(back_populates="columns")


class CatalogRelationship(Base, IdMixin, TimestampMixin):
    """Join relationships between tables (declared, imported, or AI-suggested)."""

    __tablename__ = "catalog_relationships"

    from_table_id: Mapped[str] = mapped_column(ForeignKey("catalog_tables.id"), index=True)
    from_column: Mapped[str] = mapped_column(String(255))
    to_table_id: Mapped[str] = mapped_column(ForeignKey("catalog_tables.id"), index=True)
    to_column: Mapped[str] = mapped_column(String(255))
    relationship_type: Mapped[str] = mapped_column(String(32), default="many_to_one")
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual|imported|ai|inferred
    confidence: Mapped[float | None] = mapped_column(Float)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)


class SyncRun(Base, IdMixin, TimestampMixin):
    """History of metadata synchronization executions."""

    __tablename__ = "sync_runs"

    connector_id: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16))  # full | incremental | manual
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|failed
    tables_synced: Mapped[int] = mapped_column(Integer, default=0)
    columns_synced: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
