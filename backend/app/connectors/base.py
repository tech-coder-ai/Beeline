"""Connector abstraction - the extension points for analytics sources.

V1 ships only the Hive implementation, but every pipeline stage depends on
these interfaces, never on Hive directly, so new engines (Postgres, Snowflake,
Trino, ...) are added by registering a new connector type in the registry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryResult:
    columns: list[str]
    column_types: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: int
    truncated: bool = False


@dataclass
class HarvestedColumn:
    name: str
    data_type: str
    comment: str | None = None
    is_partition: bool = False
    position: int = 0


@dataclass
class HarvestedTable:
    database: str
    name: str
    table_type: str = "TABLE"
    comment: str | None = None
    owner: str | None = None
    row_count: int | None = None
    size_bytes: int | None = None
    storage_format: str | None = None
    compression: str | None = None
    partition_columns: list[str] = field(default_factory=list)
    last_analyzed_at: str | None = None
    columns: list[HarvestedColumn] = field(default_factory=list)


@dataclass
class ColumnStatistics:
    distinct_count: int | None = None
    null_percentage: float | None = None
    min_value: str | None = None
    max_value: str | None = None
    sample_values: list[Any] = field(default_factory=list)
    top_values: list[dict] = field(default_factory=list)  # [{value, count}]


@dataclass
class CostEstimation:
    estimated_rows_scanned: int | None = None
    estimated_result_rows: int | None = None
    estimated_runtime_seconds: float | None = None
    scan_bytes: int | None = None
    partition_pruned: bool | None = None
    details: dict = field(default_factory=dict)


class ISQLDialect(ABC):
    """Dialect-specific SQL concerns."""

    @property
    @abstractmethod
    def sqlglot_dialect(self) -> str:
        """Dialect name understood by sqlglot (e.g. 'hive')."""

    @abstractmethod
    def quote_identifier(self, name: str) -> str: ...

    def dialect_hints(self) -> str:
        """Free-text hints injected into SQL-generation prompts."""
        return ""


class IQueryEstimator(ABC):
    @abstractmethod
    async def estimate(self, sql: str) -> CostEstimation: ...


class IStatisticsProvider(ABC):
    @abstractmethod
    async def column_statistics(
        self, database: str, table: str, column: str, sample_limit: int
    ) -> ColumnStatistics: ...


class IMetadataProvider(ABC):
    @abstractmethod
    async def list_databases(self) -> list[str]: ...

    @abstractmethod
    async def list_tables(self, database: str) -> list[str]: ...

    @abstractmethod
    async def describe_table(self, database: str, table: str) -> HarvestedTable: ...


class IAnalyticsConnector(ABC):
    """A configured connection to one analytics engine."""

    connector_id: str
    config: dict

    def __init__(self, connector_id: str, config: dict):
        self.connector_id = connector_id
        self.config = config

    @property
    @abstractmethod
    def dialect(self) -> ISQLDialect: ...

    @property
    @abstractmethod
    def metadata_provider(self) -> IMetadataProvider: ...

    @property
    @abstractmethod
    def statistics_provider(self) -> IStatisticsProvider: ...

    @property
    @abstractmethod
    def estimator(self) -> IQueryEstimator: ...

    @abstractmethod
    async def execute(self, sql: str, max_rows: int, timeout_seconds: int) -> QueryResult: ...

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]: ...

    async def close(self) -> None:  # noqa: B027 - optional hook
        pass
