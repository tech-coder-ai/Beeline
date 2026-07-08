"""Apache Hive connector (HiveServer2 via PyHive, wrapped for asyncio)."""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.connectors.base import (
    ColumnStatistics,
    CostEstimation,
    HarvestedColumn,
    HarvestedTable,
    IAnalyticsConnector,
    IMetadataProvider,
    IQueryEstimator,
    ISQLDialect,
    IStatisticsProvider,
    QueryResult,
)
from app.connectors.registry import register_connector
from app.core.exceptions import ConnectorError
from app.core.logging import get_logger

logger = get_logger(__name__)


class HiveDialect(ISQLDialect):
    @property
    def sqlglot_dialect(self) -> str:
        return "hive"

    def quote_identifier(self, name: str) -> str:
        return f"`{name}`"

    def dialect_hints(self) -> str:
        return (
            "Target engine is Apache Hive. Use Hive SQL syntax: backtick identifiers, "
            "date functions like date_sub/add_months/trunc, no full OUTER APPLY, "
            "prefer explicit JOIN ... ON, always filter partition columns when present."
        )


class _HiveClient:
    """Thin synchronous PyHive wrapper executed in worker threads."""

    def __init__(self, config: dict):
        self._config = config

    def _connect(self):
        from pyhive import hive

        auth = (self._config.get("auth") or "NONE").upper()
        return hive.connect(
            host=self._config.get("host", "localhost"),
            port=int(self._config.get("port", 10000)),
            username=self._config.get("username") or "hive",
            password=self._config.get("password") or None,
            database=self._config.get("database", "default"),
            auth=auth if auth != "NONE" else "NOSASL",
        )

    def run(self, sql: str, max_rows: int | None = None) -> tuple[list[str], list[str], list[list[Any]]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            if cursor.description is None:
                return [], [], []
            columns = [d[0].split(".")[-1] for d in cursor.description]
            types = [str(d[1]) if len(d) > 1 else "string" for d in cursor.description]
            rows = cursor.fetchmany(max_rows) if max_rows else cursor.fetchall()
            return columns, types, [list(r) for r in rows]
        finally:
            conn.close()


class HiveMetadataProvider(IMetadataProvider):
    def __init__(self, client: _HiveClient):
        self._client = client

    async def list_databases(self) -> list[str]:
        _, _, rows = await asyncio.to_thread(self._client.run, "SHOW DATABASES")
        return [r[0] for r in rows]

    async def list_tables(self, database: str) -> list[str]:
        _, _, rows = await asyncio.to_thread(self._client.run, f"SHOW TABLES IN `{database}`")
        return [r[0] for r in rows]

    async def describe_table(self, database: str, table: str) -> HarvestedTable:
        _, _, rows = await asyncio.to_thread(
            self._client.run, f"DESCRIBE FORMATTED `{database}`.`{table}`"
        )
        return _parse_describe_formatted(database, table, rows)


def _parse_describe_formatted(database: str, table: str, rows: list[list[Any]]) -> HarvestedTable:
    harvested = HarvestedTable(database=database, name=table)
    section = "columns"
    position = 0
    partition_names: list[str] = []

    for raw in rows:
        col0 = (raw[0] or "").strip() if len(raw) > 0 and raw[0] else ""
        col1 = (raw[1] or "").strip() if len(raw) > 1 and raw[1] else ""
        col2 = (raw[2] or "").strip() if len(raw) > 2 and raw[2] else ""

        if col0.startswith("# Partition Information"):
            section = "partitions"
            continue
        if col0.startswith("# Detailed Table Information"):
            section = "details"
            continue
        if col0.startswith("#") or (not col0 and not col1):
            continue

        if section == "columns" and col0 and col1:
            harvested.columns.append(
                HarvestedColumn(name=col0, data_type=col1, comment=col2 or None, position=position)
            )
            position += 1
        elif section == "partitions" and col0 and col1:
            partition_names.append(col0)
            harvested.columns.append(
                HarvestedColumn(
                    name=col0, data_type=col1, comment=col2 or None,
                    is_partition=True, position=position,
                )
            )
            position += 1
        elif section == "details":
            key = col0.rstrip(":")
            if key == "Owner":
                harvested.owner = col1
            elif key == "Table Type":
                harvested.table_type = "VIEW" if "VIEW" in col1.upper() else "TABLE"
            elif key in ("Comment", "comment"):
                harvested.comment = col1
            elif col1 in ("numRows", "totalSize", "rawDataSize", "transient_lastDdlTime", "comment"):
                # Table Parameters rows arrive as ('', key, value)
                if col1 == "numRows" and col2.isdigit():
                    harvested.row_count = int(col2)
                elif col1 == "totalSize" and col2.isdigit():
                    harvested.size_bytes = int(col2)
                elif col1 == "comment":
                    harvested.comment = harvested.comment or col2
            elif key == "InputFormat":
                fmt = col1.rsplit(".", 1)[-1].replace("InputFormat", "")
                harvested.storage_format = fmt or col1
            elif key == "Compressed":
                harvested.compression = col1

    harvested.partition_columns = partition_names
    return harvested


class HiveStatisticsProvider(IStatisticsProvider):
    def __init__(self, client: _HiveClient):
        self._client = client

    async def column_statistics(
        self, database: str, table: str, column: str, sample_limit: int
    ) -> ColumnStatistics:
        stats = ColumnStatistics()
        qualified = f"`{database}`.`{table}`"
        col = f"`{column}`"
        try:
            sql = (
                f"SELECT COUNT(*) AS total, COUNT({col}) AS non_null, "
                f"COUNT(DISTINCT {col}) AS distinct_c, "
                f"MIN({col}) AS min_v, MAX({col}) AS max_v "
                f"FROM (SELECT {col} FROM {qualified} LIMIT 100000) sample"
            )
            _, _, rows = await asyncio.to_thread(self._client.run, sql)
            if rows:
                total, non_null, distinct_c, min_v, max_v = rows[0]
                total = total or 0
                stats.distinct_count = distinct_c
                stats.null_percentage = round(100.0 * (total - (non_null or 0)) / total, 2) if total else None
                stats.min_value = str(min_v) if min_v is not None else None
                stats.max_value = str(max_v) if max_v is not None else None
        except Exception as exc:  # noqa: BLE001 - stats are best-effort
            logger.debug("column stats failed for %s.%s.%s: %s", database, table, column, exc)
        try:
            sql = (
                f"SELECT {col} AS v, COUNT(*) AS c FROM {qualified} "
                f"WHERE {col} IS NOT NULL GROUP BY {col} ORDER BY c DESC LIMIT {sample_limit}"
            )
            _, _, rows = await asyncio.to_thread(self._client.run, sql)
            stats.top_values = [{"value": str(r[0]), "count": r[1]} for r in rows]
            stats.sample_values = [str(r[0]) for r in rows[:sample_limit]]
        except Exception as exc:  # noqa: BLE001
            logger.debug("top values failed for %s.%s.%s: %s", database, table, column, exc)
        return stats


class HiveEstimator(IQueryEstimator):
    """Cost estimation from EXPLAIN plus table statistics."""

    def __init__(self, client: _HiveClient, connector: "HiveConnector"):
        self._client = client
        self._connector = connector

    async def estimate(self, sql: str) -> CostEstimation:
        estimation = CostEstimation()
        try:
            _, _, rows = await asyncio.to_thread(self._client.run, f"EXPLAIN {sql}")
            plan_text = "\n".join(str(r[0]) for r in rows if r)
            estimation.details["explain"] = plan_text[:4000]
            num_rows = re.findall(r"Num rows:\s*([\d,]+)", plan_text)
            if num_rows:
                counts = [int(n.replace(",", "")) for n in num_rows]
                estimation.estimated_rows_scanned = max(counts)
                estimation.estimated_result_rows = counts[-1]
            data_sizes = re.findall(r"Data size:\s*([\d,]+)", plan_text)
            if data_sizes:
                estimation.scan_bytes = max(int(n.replace(",", "")) for n in data_sizes)
            estimation.partition_pruned = "partition" in plan_text.lower()
        except Exception as exc:  # noqa: BLE001 - EXPLAIN may fail on some statements
            estimation.details["explain_error"] = str(exc)
        if estimation.estimated_rows_scanned:
            # crude throughput model: 2M rows/second scan rate on Hive
            estimation.estimated_runtime_seconds = round(
                estimation.estimated_rows_scanned / 2_000_000, 1
            )
        return estimation


@register_connector("hive")
class HiveConnector(IAnalyticsConnector):
    def __init__(self, connector_id: str, config: dict):
        super().__init__(connector_id, config)
        self._client = _HiveClient(config)
        self._dialect = HiveDialect()
        self._metadata = HiveMetadataProvider(self._client)
        self._statistics = HiveStatisticsProvider(self._client)
        self._estimator = HiveEstimator(self._client, self)

    @property
    def dialect(self) -> ISQLDialect:
        return self._dialect

    @property
    def metadata_provider(self) -> IMetadataProvider:
        return self._metadata

    @property
    def statistics_provider(self) -> IStatisticsProvider:
        return self._statistics

    @property
    def estimator(self) -> IQueryEstimator:
        return self._estimator

    async def execute(self, sql: str, max_rows: int, timeout_seconds: int) -> QueryResult:
        retry = self.config.get("retry", {})
        attempts = int(retry.get("attempts", 3))
        backoff = float(retry.get("backoff_seconds", 2))
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                columns, types, rows = await asyncio.wait_for(
                    asyncio.to_thread(self._client.run, sql, max_rows + 1),
                    timeout=timeout_seconds,
                )
                elapsed_ms = int((time.monotonic() - started) * 1000)
                truncated = len(rows) > max_rows
                return QueryResult(
                    columns=columns,
                    column_types=types,
                    rows=rows[:max_rows],
                    row_count=min(len(rows), max_rows),
                    execution_time_ms=elapsed_ms,
                    truncated=truncated,
                )
            except asyncio.TimeoutError as exc:
                raise ConnectorError(
                    f"Query exceeded the {timeout_seconds}s timeout and was cancelled."
                ) from exc
            except Exception as exc:  # noqa: BLE001 - transient failures retried
                last_error = exc
                logger.warning("Hive execute attempt %d/%d failed: %s", attempt, attempts, exc)
                if attempt < attempts:
                    await asyncio.sleep(backoff * attempt)
        raise ConnectorError(f"Hive execution failed after {attempts} attempts: {last_error}")

    async def test_connection(self) -> tuple[bool, str]:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._client.run, "SELECT 1"),
                timeout=int(self.config.get("connect_timeout_seconds", 15)),
            )
            return True, "Connection successful"
        except Exception as exc:  # noqa: BLE001
            return False, f"Connection failed: {exc}"
