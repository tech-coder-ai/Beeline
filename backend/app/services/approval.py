"""Approval workflow: review queue for AI/imported metadata with versioning,
rollback and a full audit trail."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, ValidationFailed
from app.models.catalog import CatalogColumn, CatalogTable
from app.models.governance import ApprovalItem, MetadataVersion
from app.models.semantic import GlossaryTerm, Synonym
from app.services.audit import audit


class ApprovalService:
    async def list_pending(self, db: AsyncSession, entity_type: str | None = None,
                           status: str = "pending", limit: int = 200) -> list[ApprovalItem]:
        stmt = select(ApprovalItem).where(ApprovalItem.status == status)
        if entity_type:
            stmt = stmt.where(ApprovalItem.entity_type == entity_type)
        stmt = stmt.order_by(ApprovalItem.created_at.desc()).limit(limit)
        return list((await db.execute(stmt)).scalars())

    async def counts(self, db: AsyncSession) -> dict:
        rows = (
            await db.execute(
                select(ApprovalItem.entity_type, func.count())
                .where(ApprovalItem.status == "pending")
                .group_by(ApprovalItem.entity_type)
            )
        ).all()
        return {etype: count for etype, count in rows}

    async def decide(self, db: AsyncSession, item_id: str, action: str,
                     edited_value: str | None = None, note: str | None = None,
                     user_id: str = "admin") -> ApprovalItem:
        item = await db.get(ApprovalItem, item_id)
        if not item:
            raise NotFound("Approval item not found")
        if item.status != "pending":
            raise ValidationFailed(f"Item already {item.status}")

        item.reviewed_by = user_id
        item.reviewed_at = datetime.now(timezone.utc)
        item.review_note = note

        if action == "reject":
            item.status = "rejected"
        elif action in ("approve", "edit"):
            value = edited_value if action == "edit" and edited_value is not None else item.proposed_value
            item.final_value = value
            item.status = "edited" if action == "edit" else "approved"
            await self._apply(db, item, value)
        else:
            raise ValidationFailed(f"Unknown action '{action}'")

        await audit(db, user_id, f"metadata.{item.status}", entity_type=item.entity_type,
                    entity_id=item.entity_id, detail={
                        "label": item.entity_label, "field": item.field, "value": item.final_value,
                    })
        return item

    async def bulk_decide(self, db: AsyncSession, ids: list[str], action: str,
                          note: str | None = None, user_id: str = "admin") -> dict:
        succeeded, failed = 0, 0
        for item_id in ids:
            try:
                await self.decide(db, item_id, action, note=note, user_id=user_id)
                succeeded += 1
            except (NotFound, ValidationFailed):
                failed += 1
        return {"succeeded": succeeded, "failed": failed}

    async def rollback(self, db: AsyncSession, version_id: str, user_id: str = "admin") -> None:
        version = await db.get(MetadataVersion, version_id)
        if not version:
            raise NotFound("Version not found")
        await self._write_value(db, version.entity_type, version.entity_id,
                                version.field, version.old_value)
        await self._record_version(db, version.entity_type, version.entity_id, version.field,
                                   version.new_value, version.old_value, user_id, "rollback")
        await audit(db, user_id, "metadata.rollback", entity_type=version.entity_type,
                    entity_id=version.entity_id, detail={"field": version.field})

    async def history(self, db: AsyncSession, entity_type: str, entity_id: str) -> list[MetadataVersion]:
        stmt = (
            select(MetadataVersion)
            .where(MetadataVersion.entity_type == entity_type,
                   MetadataVersion.entity_id == entity_id)
            .order_by(MetadataVersion.created_at.desc())
        )
        return list((await db.execute(stmt)).scalars())

    # ------------------------------------------------------------ application
    async def _apply(self, db: AsyncSession, item: ApprovalItem, value: str) -> None:
        old_value: str | None = item.current_value

        if item.entity_type == "table_description":
            table = await self._require(db, CatalogTable, item.entity_id)
            table.description = value
        elif item.entity_type == "column_description":
            column = await self._require(db, CatalogColumn, item.entity_id)
            column.description = value
            payload = item.proposed_payload or {}
            if payload.get("semantic_type"):
                column.inferred_semantic_type = payload["semantic_type"]
            if payload.get("is_pii"):
                column.is_pii = True
            if payload.get("tags"):
                column.tags = sorted(set((column.tags or []) + payload["tags"]))
        elif item.entity_type == "tag":
            table = await self._require(db, CatalogTable, item.entity_id)
            table.tags = json.loads(value) if value.startswith("[") else [value]
        elif item.entity_type == "classification":
            table = await self._require(db, CatalogTable, item.entity_id)
            table.classification = value
        elif item.entity_type == "glossary_term":
            existing = (
                await db.execute(
                    select(GlossaryTerm).where(GlossaryTerm.term == item.entity_label)
                )
            ).scalar_one_or_none()
            if existing is None:
                term = GlossaryTerm(
                    term=item.entity_label, definition=value, source="ai", status="approved"
                )
                db.add(term)
                await db.flush()
                for synonym in (item.proposed_payload or {}).get("synonyms", []):
                    db.add(Synonym(term_id=term.id, synonym=synonym, source="ai"))
            else:
                existing.definition = value
        elif item.entity_type == "synonym":
            term = (
                await db.execute(
                    select(GlossaryTerm).where(GlossaryTerm.term == item.entity_label)
                )
            ).scalar_one_or_none()
            if term:
                db.add(Synonym(term_id=term.id, synonym=value, source="learned"))
        else:
            raise ValidationFailed(f"Unsupported entity type '{item.entity_type}'")

        await self._record_version(
            db, item.entity_type, item.entity_id, item.field,
            old_value, value, item.reviewed_by or "admin", "approval", item.id,
        )

    async def _write_value(self, db: AsyncSession, entity_type: str, entity_id: str,
                           field: str, value: str | None) -> None:
        model = {
            "table_description": CatalogTable, "tag": CatalogTable,
            "classification": CatalogTable, "column_description": CatalogColumn,
        }.get(entity_type)
        if model is None:
            raise ValidationFailed(f"Rollback unsupported for '{entity_type}'")
        row = await self._require(db, model, entity_id)
        if field == "tags" and value:
            row.tags = json.loads(value) if value.startswith("[") else [value]
        else:
            setattr(row, field, value)

    async def _record_version(self, db: AsyncSession, entity_type: str, entity_id: str,
                              field: str, old_value: str | None, new_value: str | None,
                              user: str, source: str, approval_id: str | None = None) -> None:
        latest = (
            await db.execute(
                select(func.max(MetadataVersion.version)).where(
                    MetadataVersion.entity_type == entity_type,
                    MetadataVersion.entity_id == entity_id,
                    MetadataVersion.field == field,
                )
            )
        ).scalar() or 0
        db.add(MetadataVersion(
            entity_type=entity_type, entity_id=entity_id, field=field,
            old_value=old_value, new_value=new_value, version=latest + 1,
            changed_by=user, change_source=source, approval_id=approval_id,
        ))

    @staticmethod
    async def _require(db: AsyncSession, model, entity_id: str):
        row = await db.get(model, entity_id)
        if row is None:
            raise NotFound(f"{model.__name__} {entity_id} no longer exists")
        return row


approval_service = ApprovalService()
