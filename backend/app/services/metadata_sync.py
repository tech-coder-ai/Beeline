"""Hive metadata synchronization service.

Harvests databases/tables/columns/statistics from the analytics source into
the application metadata repository. Supports full, incremental and scheduled
refresh; the NL pipeline only ever reads the repository.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors.base import IAnalyticsConnector
from app.connectors.registry import get_connector
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.catalog import CatalogColumn, CatalogDatabase, CatalogTable, SyncRun

logger = get_logger(__name__)

_sync_lock = asyncio.Lock()


class MetadataSyncService:
    async def sync(self, connector_id: str | None = None, mode: str = "incremental") -> SyncRun:
        """Runs a synchronization in its own DB session (callable from background)."""
        async with _sync_lock:
            factory = get_session_factory()
            async with factory() as db:
                connector = get_connector(connector_id)
                run = SyncRun(connector_id=connector.connector_id, mode=mode)
                db.add(run)
                await db.flush()
                try:
                    stats = await self._sync_catalog(db, connector, mode)
                    run.tables_synced = stats["tables"]
                    run.columns_synced = stats["columns"]
                    run.status = "success"
                except Exception as exc:  # noqa: BLE001
                    logger.exception("metadata sync failed")
                    run.status = "failed"
                    run.error = str(exc)[:2000]
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
                return run

    async def _sync_catalog(self, db: AsyncSession, connector: IAnalyticsConnector,
                            mode: str) -> dict:
        settings = get_settings()
        allowed = set(connector.config.get("allowed_schemas") or [])
        max_tables = settings.get("metadata_sync.max_tables_per_run", 500)
        sample_limit = settings.get("metadata_sync.sample_values_per_column", 8)
        collect_stats = settings.get("metadata_sync.collect_distinct_counts", True)
        now = datetime.now(timezone.utc)

        provider = connector.metadata_provider
        databases = await provider.list_databases()
        if allowed:
            databases = [d for d in databases if d in allowed]

        tables_synced = columns_synced = 0
        seen_table_ids: set[str] = set()

        for db_name in databases:
            catalog_db = (
                await db.execute(
                    select(CatalogDatabase).where(
                        CatalogDatabase.connector_id == connector.connector_id,
                        CatalogDatabase.name == db_name,
                    )
                )
            ).scalar_one_or_none()
            if catalog_db is None:
                catalog_db = CatalogDatabase(connector_id=connector.connector_id, name=db_name)
                db.add(catalog_db)
                await db.flush()

            table_names = await provider.list_tables(db_name)
            catalog_db.table_count = len(table_names)
            catalog_db.last_synced_at = now

            for table_name in table_names:
                if tables_synced >= max_tables:
                    break
                existing = (
                    await db.execute(
                        select(CatalogTable)
                        .options(selectinload(CatalogTable.columns))
                        .where(
                            CatalogTable.database_id == catalog_db.id,
                            CatalogTable.name == table_name,
                        )
                    )
                ).scalar_one_or_none()

                # incremental mode: skip recently synced, unchanged tables
                if (
                    mode == "incremental" and existing and existing.last_synced_at
                    and (now - existing.last_synced_at.replace(tzinfo=timezone.utc)).total_seconds()
                    < settings.get("metadata_sync.interval_minutes", 720) * 60
                ):
                    seen_table_ids.add(existing.id)
                    continue

                harvested = await provider.describe_table(db_name, table_name)
                table = existing or CatalogTable(database_id=catalog_db.id, name=table_name)
                if existing is None:
                    db.add(table)
                table.table_type = harvested.table_type
                table.technical_comment = harvested.comment
                table.owner = table.owner or harvested.owner
                table.row_count = harvested.row_count
                table.size_bytes = harvested.size_bytes
                table.storage_format = harvested.storage_format
                table.compression = harvested.compression
                table.partition_columns = harvested.partition_columns
                table.last_synced_at = now
                table.is_active = True
                await db.flush()
                seen_table_ids.add(table.id)

                existing_cols = {c.name: c for c in (existing.columns if existing else [])}
                harvested_names = set()
                for hcol in harvested.columns:
                    harvested_names.add(hcol.name)
                    col = existing_cols.get(hcol.name) or CatalogColumn(
                        table_id=table.id, name=hcol.name
                    )
                    if hcol.name not in existing_cols:
                        db.add(col)
                    col.position = hcol.position
                    col.data_type = hcol.data_type
                    col.technical_comment = hcol.comment
                    col.is_partition = hcol.is_partition
                    columns_synced += 1
                # drop columns removed upstream
                for name, col in existing_cols.items():
                    if name not in harvested_names:
                        await db.delete(col)
                await db.flush()

                if collect_stats:
                    await self._collect_statistics(db, connector, table, db_name, sample_limit)
                tables_synced += 1

        # stale detection: tables no longer present upstream
        all_tables = (
            await db.execute(
                select(CatalogTable)
                .join(CatalogDatabase, CatalogTable.database_id == CatalogDatabase.id)
                .where(CatalogDatabase.connector_id == connector.connector_id)
            )
        ).scalars().all()
        if mode == "full":
            for table in all_tables:
                if table.id not in seen_table_ids and table.is_active:
                    table.is_active = False
                    logger.info("marking stale table inactive: %s", table.name)

        return {"tables": tables_synced, "columns": columns_synced}

    async def _collect_statistics(self, db: AsyncSession, connector: IAnalyticsConnector,
                                  table: CatalogTable, db_name: str, sample_limit: int) -> None:
        columns = (
            await db.execute(select(CatalogColumn).where(CatalogColumn.table_id == table.id))
        ).scalars().all()
        for col in columns:
            if col.is_partition:
                continue
            try:
                stats = await connector.statistics_provider.column_statistics(
                    db_name, table.name, col.name, sample_limit
                )
                col.distinct_count = stats.distinct_count
                col.null_percentage = stats.null_percentage
                col.min_value = stats.min_value
                col.max_value = stats.max_value
                col.sample_values = stats.sample_values[:sample_limit]
                col.top_values = stats.top_values[:sample_limit]
                if table.row_count and stats.distinct_count:
                    col.distinct_percentage = round(
                        100.0 * stats.distinct_count / max(table.row_count, 1), 2
                    )
            except Exception as exc:  # noqa: BLE001 - stats are best-effort
                logger.debug("stats skipped for %s.%s: %s", table.name, col.name, exc)


metadata_sync_service = MetadataSyncService()


async def scheduled_sync_loop() -> None:
    """Background task started at app startup: periodic incremental refresh."""
    settings = get_settings()
    while True:
        interval = max(settings.get("metadata_sync.interval_minutes", 720), 5) * 60
        await asyncio.sleep(interval)
        if not settings.get("metadata_sync.enabled", True):
            continue
        try:
            await metadata_sync_service.sync(mode="incremental")
        except Exception:  # noqa: BLE001
            logger.exception("scheduled metadata sync failed")
