"""LLM metadata enrichment.

Generates business descriptions, tags, classifications, semantic types and
glossary suggestions from harvested technical metadata. Nothing is applied
directly - every proposal enters the approval queue.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import NotFound
from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.models.catalog import CatalogTable
from app.models.governance import ApprovalItem
from app.schemas.api import TableEnrichRequest
from app.services.metadata_sync import metadata_sync_service

logger = get_logger(__name__)


class EnrichmentService:
    async def enrich_tables(
        self,
        db: AsyncSession,
        table_ids: list[str] | None = None,
        batch_size: int | None = None,
    ) -> dict:
        settings = get_settings()
        if not settings.get("enrichment.enabled", True):
            return {"enriched": 0, "proposals": 0, "skipped": "enrichment disabled"}

        effective_batch = (
            batch_size if batch_size is not None else settings.get("enrichment.batch_size", 10)
        )

        stmt = (
            select(CatalogTable)
            .options(selectinload(CatalogTable.columns), selectinload(CatalogTable.database))
            .where(CatalogTable.is_active.is_(True))
        )
        if table_ids:
            stmt = stmt.where(CatalogTable.id.in_(table_ids))
        else:
            stmt = stmt.where(
                (CatalogTable.description.is_(None)) | (CatalogTable.description == "")
            )
            if effective_batch > 0:
                stmt = stmt.limit(effective_batch)
        tables = (await db.execute(stmt)).scalars().all()

        proposals = 0
        for table in tables:
            try:
                proposals += await self._enrich_one(db, table)
            except Exception as exc:  # noqa: BLE001 - continue with other tables
                logger.warning("enrichment failed for %s: %s", table.name, exc)
        return {"enriched": len(tables), "proposals": proposals, "batch_size": effective_batch}

    async def enrich_table(
        self, db: AsyncSession, table_id: str, request: TableEnrichRequest | None = None
    ) -> dict:
        settings = get_settings()
        if not settings.get("enrichment.enabled", True):
            return {"enriched": 0, "proposals": 0, "skipped": "enrichment disabled"}

        table = (
            await db.execute(
                select(CatalogTable)
                .options(selectinload(CatalogTable.columns), selectinload(CatalogTable.database))
                .where(CatalogTable.id == table_id, CatalogTable.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if not table:
            raise NotFound("Table not found")

        if request:
            if request.description:
                table.description = request.description.strip()
            if request.tags:
                table.tags = request.tags
            await db.flush()

        row_refresh: dict = {}
        should_refresh = request is None or request.refresh_row_count is not False
        if should_refresh and table.row_count is None:
            try:
                row_refresh = await metadata_sync_service.refresh_table_stats(db, table_id)
                await db.refresh(table)
            except Exception as exc:  # noqa: BLE001
                logger.warning("row count refresh failed for %s: %s", table.name, exc)
                row_refresh = {"row_count_refresh": "failed"}

        user_context = self._build_user_context(table, request)
        proposals = await self._enrich_one(db, table, user_context)

        result = {
            "enriched": 1,
            "proposals": proposals,
            "table_id": table_id,
            "row_count": table.row_count,
            "note": "AI proposals were queued for approval. Review them in the Approvals tab.",
        }
        if row_refresh:
            result["row_count_refresh"] = row_refresh
        return result

    def _build_user_context(self, table: CatalogTable, request: TableEnrichRequest | None) -> dict:
        ctx: dict = {}
        if table.description:
            ctx["description"] = table.description
        if table.tags:
            ctx["tags"] = table.tags
        if request and request.glossary_hints:
            hints = [
                {"term": h.term.strip(), "definition": (h.definition or "").strip()}
                for h in request.glossary_hints
                if h.term.strip()
            ]
            if hints:
                ctx["glossary_hints"] = hints
        return ctx

    async def _enrich_one(
        self, db: AsyncSession, table: CatalogTable, user_context: dict | None = None
    ) -> int:
        payload = {
            "table": f"{table.database.name}.{table.name}",
            "technical_comment": table.technical_comment,
            "row_count": table.row_count,
            "partition_columns": table.partition_columns,
            "columns": [
                {
                    "name": c.name,
                    "data_type": c.data_type,
                    "comment": c.technical_comment,
                    "sample_values": (c.sample_values or [])[:5],
                    "top_values": (c.top_values or [])[:3],
                    "null_percentage": c.null_percentage,
                    "distinct_count": c.distinct_count,
                }
                for c in table.columns
            ],
        }
        if user_context:
            payload["user_context"] = user_context
        llm = get_llm()
        parsed, _ = await llm.complete_json(
            prompts.ENRICHMENT_SYSTEM, json.dumps(payload, default=str)
        )
        if not parsed:
            return 0

        label = f"{table.database.name}.{table.name}"
        confidence = float(parsed.get("confidence") or 0.5)
        rationale = str(parsed.get("rationale") or "")
        count = 0

        if parsed.get("table_description"):
            db.add(ApprovalItem(
                entity_type="table_description", entity_id=table.id, entity_label=label,
                field="description", current_value=table.description,
                proposed_value=str(parsed["table_description"]),
                confidence=confidence, rationale=rationale,
            ))
            count += 1
        if parsed.get("table_tags"):
            db.add(ApprovalItem(
                entity_type="tag", entity_id=table.id, entity_label=label,
                field="tags", current_value=json.dumps(table.tags or []),
                proposed_value=json.dumps(parsed["table_tags"]),
                confidence=confidence, rationale=rationale,
            ))
            count += 1
        if parsed.get("classification"):
            db.add(ApprovalItem(
                entity_type="classification", entity_id=table.id, entity_label=label,
                field="classification", current_value=table.classification,
                proposed_value=str(parsed["classification"]),
                confidence=confidence, rationale=rationale,
            ))
            count += 1

        columns_by_name = {c.name: c for c in table.columns}
        for col_proposal in parsed.get("columns", []):
            col = columns_by_name.get(col_proposal.get("name"))
            if not col:
                continue  # anti-hallucination: never create approval for unknown columns
            col_label = f"{label}.{col.name}"
            col_conf = float(col_proposal.get("confidence") or confidence)
            if col_proposal.get("description"):
                db.add(ApprovalItem(
                    entity_type="column_description", entity_id=col.id, entity_label=col_label,
                    field="description", current_value=col.description,
                    proposed_value=str(col_proposal["description"]), confidence=col_conf,
                    proposed_payload={
                        "semantic_type": col_proposal.get("semantic_type"),
                        "is_pii": bool(col_proposal.get("is_pii")),
                        "tags": col_proposal.get("tags") or [],
                    },
                ))
                count += 1

        for term in parsed.get("glossary_suggestions", []):
            if not term.get("term") or not term.get("definition"):
                continue
            db.add(ApprovalItem(
                entity_type="glossary_term", entity_id=table.id, entity_label=str(term["term"]),
                field="glossary", current_value=None,
                proposed_value=str(term["definition"]),
                proposed_payload={"synonyms": term.get("synonyms") or []},
                confidence=confidence, rationale=f"Suggested while documenting {label}",
            ))
            count += 1
        return count


enrichment_service = EnrichmentService()
