"""SQL Optimizer: normalization, automatic LIMIT injection, partition hints."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.core.config import get_settings
from app.core.logging import get_logger
from app.pipeline.types import PipelineContext

logger = get_logger(__name__)


class SQLOptimizer:
    def optimize(self, sql: str, dialect: str, ctx: PipelineContext | None = None) -> str:
        settings = get_settings()
        try:
            tree = sqlglot.parse_one(sql, read=dialect)
        except Exception as exc:  # noqa: BLE001 - validator already parsed; be safe anyway
            logger.warning("optimizer parse failed: %s", exc)
            return sql

        # Automatic LIMIT injection when the outermost select has none
        if isinstance(tree, (exp.Select, exp.Union)) and not tree.args.get("limit"):
            default_limit = int(settings.get("guardrails.default_limit", 1000))
            tree = tree.limit(default_limit)
            if ctx is not None:
                ctx.validation_warnings.append(
                    f"No LIMIT specified; automatically capped at {default_limit} rows."
                )

        # Partition-filter advisory: warn when a partitioned table lacks a
        # predicate on any of its partition columns.
        if ctx is not None and ctx.resolved_tables:
            where = tree.args.get("where")
            where_cols = {
                c.name.lower() for c in (where.find_all(exp.Column) if where else [])
            }
            referenced = {
                ".".join(p for p in [t.db, t.name] if p).lower()
                for t in tree.find_all(exp.Table)
            }
            for table in ctx.resolved_tables:
                if table.qualified_name.lower() not in referenced or not table.partition_columns:
                    continue
                if not any(pc.lower() in where_cols for pc in table.partition_columns):
                    ctx.validation_warnings.append(
                        f"{table.qualified_name} is partitioned by "
                        f"{', '.join(table.partition_columns)} but the query does not filter on it; "
                        "a full scan is likely."
                    )

        try:
            return tree.sql(dialect=dialect, pretty=True)
        except Exception:  # noqa: BLE001
            return sql
