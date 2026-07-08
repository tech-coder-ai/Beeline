"""Query Executor: runs validated SQL through the connector with result caching."""
from __future__ import annotations

import hashlib

from app.connectors.base import IAnalyticsConnector
from app.core.cache import cache
from app.core.config import get_settings
from app.pipeline.types import PipelineContext


class QueryExecutor:
    async def run(self, ctx: PipelineContext, connector: IAnalyticsConnector) -> None:
        settings = get_settings()
        sql = ctx.optimized_sql or ctx.sql or ""
        max_rows = int(settings.get("guardrails.max_result_rows", 10000))
        timeout = int(settings.get("guardrails.query_timeout_seconds", 300))

        cache_key = "result:" + hashlib.sha256(
            f"{connector.connector_id}:{sql}".encode()
        ).hexdigest()
        cached = await cache.get_json(cache_key)
        if cached:
            ctx.result_columns = cached["columns"]
            ctx.result_types = cached["types"]
            ctx.result_rows = cached["rows"]
            ctx.row_count = cached["row_count"]
            ctx.execution_time_ms = 0
            ctx.truncated = cached.get("truncated", False)
            ctx.cache_hit = True
            return

        result = await connector.execute(sql, max_rows=max_rows, timeout_seconds=timeout)
        ctx.result_columns = result.columns
        ctx.result_types = result.column_types
        ctx.result_rows = result.rows
        ctx.row_count = result.row_count
        ctx.execution_time_ms = result.execution_time_ms
        ctx.truncated = result.truncated

        await cache.set_json(
            cache_key,
            {
                "columns": result.columns,
                "types": result.column_types,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
            },
            ttl=int(settings.get("cache.result_ttl_seconds", 900)),
        )
