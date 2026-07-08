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
from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.models.catalog import CatalogTable
from app.models.governance import ApprovalItem

logger = get_logger(__name__)


class EnrichmentService:
    async def enrich_tables(self, db: AsyncSession, table_ids: list[str] | None = None) -> dict:
        settings = get_settings()
        if not settings.get("enrichment.enabled", True):
            return {"enriched": 0, "proposals": 0, "skipped": "enrichment disabled"}

        stmt = (
            select(CatalogTable)
            .options(selectinload(CatalogTable.columns), selectinload(CatalogTable.database))
            .where(CatalogTable.is_active.is_(True))
        )
        if table_ids:
            stmt = stmt.where(CatalogTable.id.in_(table_ids))
        else:
            stmt = stmt.where(CatalogTable.description.is_(None)).limit(
                settings.get("enrichment.batch_size", 10)
            )
        tables = (await db.execute(stmt)).scalars().all()

        proposals = 0
        for table in tables:
            try:
                proposals += await self._enrich_one(db, table)
            except Exception as exc:  # noqa: BLE001 - continue with other tables
                logger.warning("enrichment failed for %s: %s", table.name, exc)
        return {"enriched": len(tables), "proposals": proposals}

    async def _enrich_one(self, db: AsyncSession, table: CatalogTable) -> int:
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
