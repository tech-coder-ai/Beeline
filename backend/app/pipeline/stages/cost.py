"""Query Cost Estimator: predicts scan size before execution and blocks
queries exceeding configured thresholds, with actionable suggestions."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.connectors.base import IAnalyticsConnector
from app.core.config import get_settings
from app.core.logging import get_logger
from app.pipeline.types import PipelineContext

logger = get_logger(__name__)


class CostEstimator:
    async def run(self, ctx: PipelineContext, connector: IAnalyticsConnector) -> None:
        settings = get_settings()
        sql = ctx.optimized_sql or ctx.sql or ""
        estimate: dict = {
            "estimated_rows_scanned": None,
            "estimated_result_rows": None,
            "estimated_runtime_seconds": None,
            "scan_bytes": None,
            "partition_pruned": None,
            "join_count": 0,
            "warnings": [],
            "blocked": False,
            "block_reason": None,
            "suggestions": [],
        }

        # catalog-statistics estimate (fast, no engine round-trip)
        catalog_rows = self._catalog_scan_estimate(ctx, sql, connector.dialect.sqlglot_dialect, estimate)

        # engine estimate (EXPLAIN) - best effort
        try:
            engine_est = await connector.estimator.estimate(sql)
            if engine_est.estimated_rows_scanned:
                estimate["estimated_rows_scanned"] = engine_est.estimated_rows_scanned
            if engine_est.estimated_result_rows:
                estimate["estimated_result_rows"] = engine_est.estimated_result_rows
            estimate["scan_bytes"] = engine_est.scan_bytes
            estimate["partition_pruned"] = engine_est.partition_pruned
            if engine_est.estimated_runtime_seconds:
                estimate["estimated_runtime_seconds"] = engine_est.estimated_runtime_seconds
        except Exception as exc:  # noqa: BLE001
            logger.debug("engine estimation unavailable: %s", exc)

        if estimate["estimated_rows_scanned"] is None:
            estimate["estimated_rows_scanned"] = catalog_rows
        if estimate["estimated_runtime_seconds"] is None and estimate["estimated_rows_scanned"]:
            estimate["estimated_runtime_seconds"] = round(estimate["estimated_rows_scanned"] / 2_000_000, 1)

        scanned = estimate["estimated_rows_scanned"] or 0
        warn_rows = settings.get("cost.warn_estimated_rows_scanned", 50_000_000)
        max_rows = settings.get("cost.max_estimated_rows_scanned", 500_000_000)
        max_runtime = settings.get("cost.max_estimated_runtime_seconds", 600)

        if scanned > warn_rows:
            estimate["warnings"].append(
                f"Query is estimated to scan approximately {scanned:,} rows."
            )
        if scanned > max_rows:
            minutes = round((estimate["estimated_runtime_seconds"] or 0) / 60) or "several"
            estimate["blocked"] = True
            estimate["block_reason"] = (
                f"This query is estimated to scan approximately {scanned:,} rows and may take "
                f"around {minutes} minutes. Please refine your filters."
            )
        elif (estimate["estimated_runtime_seconds"] or 0) > max_runtime:
            estimate["blocked"] = True
            estimate["block_reason"] = (
                f"Estimated runtime {estimate['estimated_runtime_seconds']:.0f}s exceeds the "
                f"{max_runtime}s limit. Please narrow the query."
            )

        if estimate["blocked"]:
            estimate["suggestions"] = self._suggestions(ctx)
        ctx.cost = estimate

    @staticmethod
    def _catalog_scan_estimate(ctx: PipelineContext, sql: str, dialect: str, estimate: dict) -> int | None:
        try:
            tree = sqlglot.parse_one(sql, read=dialect)
        except Exception:  # noqa: BLE001
            return None
        referenced = {
            ".".join(p for p in [t.db, t.name] if p).lower() for t in tree.find_all(exp.Table)
        }
        estimate["join_count"] = len(list(tree.find_all(exp.Join)))
        total = 0
        found = False
        for table in ctx.resolved_tables:
            if table.qualified_name.lower() in referenced and table.row_count:
                total += table.row_count
                found = True
        return total if found else None

    @staticmethod
    def _suggestions(ctx: PipelineContext) -> list[str]:
        suggestions = ["Add a date range filter to reduce the scanned period."]
        for table in ctx.resolved_tables:
            if table.partition_columns:
                suggestions.append(
                    f"Filter {table.qualified_name} on its partition column(s): "
                    f"{', '.join(table.partition_columns)}."
                )
        suggestions.append("Aggregate at a coarser grain (e.g. monthly instead of daily).")
        suggestions.append("Limit the result to the top N categories you care about.")
        return suggestions[:4]
