"""CSV import for synonyms, business terms, and abbreviations."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ValidationFailed
from app.models.catalog import CatalogDatabase, CatalogTable
from app.models.semantic import Abbreviation, BusinessTerm, GlossaryTerm, Synonym
from app.services.import_export import import_service as metadata_import


class SemanticImportService:
    SUPPORTED_TYPES = {"synonyms", "business_terms", "abbreviations", "metadata"}

    def parse(self, filename: str, content: bytes) -> list[dict]:
        return metadata_import.parse(filename, content)

    def detect_type(self, rows: list[dict]) -> str:
        if not rows:
            raise ValidationFailed("The file contains no data rows")
        keys = set(rows[0].keys())
        if {"abbreviation", "entity", "value"} <= keys or {"abbrev", "entity", "value"} <= keys:
            return "abbreviations"
        if {"abbreviation", "canonical"} <= keys or {"abbrev", "canonical"} <= keys:
            return "abbreviations"
        if {"term", "entity", "column_name", "value"} <= keys:
            return "business_terms"
        if {"canonical", "synonym"} <= keys or {"canonical", "synonyms"} <= keys:
            return "synonyms"
        if "table" in keys:
            return "metadata"
        raise ValidationFailed(
            "Could not detect import type. Use columns for synonyms (canonical,synonym), "
            "business_terms (term,entity,column_name,value), or abbreviations (abbreviation,entity,value)."
        )

    async def preview(self, db: AsyncSession, rows: list[dict], import_type: str | None) -> dict:
        kind = import_type or self.detect_type(rows)
        if kind == "metadata":
            return await metadata_import.preview(db, rows)
        if kind == "synonyms":
            return self._preview_synonyms(rows)
        if kind == "business_terms":
            return await self._preview_business_terms(db, rows)
        if kind == "abbreviations":
            return self._preview_abbreviations(rows)
        raise ValidationFailed(f"Unsupported import type: {kind}")

    async def commit(self, db: AsyncSession, rows: list[dict], import_type: str | None) -> dict:
        kind = import_type or self.detect_type(rows)
        if kind == "metadata":
            return await metadata_import.commit(db, rows)
        if kind == "synonyms":
            return await self._commit_synonyms(db, rows)
        if kind == "business_terms":
            return await self._commit_business_terms(db, rows)
        if kind == "abbreviations":
            return await self._commit_abbreviations(db, rows)
        raise ValidationFailed(f"Unsupported import type: {kind}")

    @staticmethod
    def _split_values(raw: str) -> list[str]:
        return [part.strip() for part in raw.split(",") if part.strip()]

    def _preview_synonyms(self, rows: list[dict]) -> dict:
        changes, unmatched = [], []
        for index, row in enumerate(rows):
            canonical = (row.get("canonical") or "").strip()
            if not canonical:
                unmatched.append({"row": index + 1, "reason": "missing canonical"})
                continue
            synonym_values = []
            if row.get("synonym"):
                synonym_values.append(row["synonym"].strip())
            if row.get("synonyms"):
                synonym_values.extend(self._split_values(row["synonyms"]))
            if not synonym_values:
                unmatched.append({"row": index + 1, "reason": "missing synonym(s)"})
                continue
            for syn in synonym_values:
                changes.append(
                    {
                        "entity_type": "synonym",
                        "label": canonical,
                        "field": "synonym",
                        "current": None,
                        "proposed": syn,
                    }
                )
        return {
            "import_type": "synonyms",
            "matched_rows": len(rows) - len(unmatched),
            "unmatched": unmatched,
            "changes": changes,
        }

    async def _preview_business_terms(self, db: AsyncSession, rows: list[dict]) -> dict:
        changes, unmatched = [], []
        for index, row in enumerate(rows):
            term = (row.get("term") or "").strip()
            entity = (row.get("entity") or "").strip()
            column_name = (row.get("column_name") or row.get("column") or "").strip()
            value = (row.get("value") or "").strip()
            if not term or not entity or not column_name or not value:
                unmatched.append({"row": index + 1, "reason": "term, entity, column_name, and value are required"})
                continue
            table_id = await self._resolve_table_id(db, entity)
            changes.append(
                {
                    "entity_type": "business_term",
                    "label": term,
                    "field": "binding",
                    "current": None,
                    "proposed": f"{entity}.{column_name} = {value}",
                    "payload": {
                        "term": term,
                        "entity": entity,
                        "column_name": column_name,
                        "value": value,
                        "table_id": table_id,
                    },
                }
            )
        return {
            "import_type": "business_terms",
            "matched_rows": len(rows) - len(unmatched),
            "unmatched": unmatched,
            "changes": changes,
        }

    def _preview_abbreviations(self, rows: list[dict]) -> dict:
        changes, unmatched = [], []
        for index, row in enumerate(rows):
            abbrev = (row.get("abbreviation") or row.get("abbrev") or "").strip()
            entity = (row.get("entity") or row.get("canonical") or "").strip()
            value = (row.get("value") or row.get("canonical") or "").strip()
            if not abbrev or not entity or not value:
                unmatched.append({"row": index + 1, "reason": "abbreviation, entity, and value are required"})
                continue
            changes.append(
                {
                    "entity_type": "abbreviation",
                    "label": abbrev,
                    "field": "binding",
                    "current": None,
                    "proposed": f"{entity} = {value}",
                }
            )
        return {
            "import_type": "abbreviations",
            "matched_rows": len(rows) - len(unmatched),
            "unmatched": unmatched,
            "changes": changes,
        }

    async def _commit_synonyms(self, db: AsyncSession, rows: list[dict]) -> dict:
        preview = self._preview_synonyms(rows)
        created, updated = 0, 0
        for row in rows:
            canonical = (row.get("canonical") or "").strip()
            if not canonical:
                continue
            synonym_values = []
            if row.get("synonym"):
                synonym_values.append(row["synonym"].strip())
            if row.get("synonyms"):
                synonym_values.extend(self._split_values(row["synonyms"]))
            if not synonym_values:
                continue
            term = await self._resolve_canonical(db, canonical)
            existing = {s.synonym.lower() for s in term.synonyms}
            for syn in synonym_values:
                if syn.lower() in existing:
                    continue
                db.add(Synonym(term_id=term.id, synonym=syn, source="imported"))
                created += 1
            updated += 1
        await db.commit()
        return {**preview, "applied": updated, "synonyms_added": created}

    async def _commit_business_terms(self, db: AsyncSession, rows: list[dict]) -> dict:
        preview = await self._preview_business_terms(db, rows)
        applied = 0
        for change in preview["changes"]:
            payload = change["payload"]
            db.add(
                BusinessTerm(
                    term=payload["term"],
                    entity=payload["entity"],
                    column_name=payload["column_name"],
                    value=payload["value"],
                    table_id=payload.get("table_id"),
                    source="imported",
                    status="approved",
                )
            )
            applied += 1
        await db.commit()
        return {**preview, "applied": applied}

    async def _commit_abbreviations(self, db: AsyncSession, rows: list[dict]) -> dict:
        preview = self._preview_abbreviations(rows)
        applied = 0
        for row in rows:
            abbrev = (row.get("abbreviation") or row.get("abbrev") or "").strip()
            entity = (row.get("entity") or row.get("canonical") or "").strip()
            value = (row.get("value") or row.get("canonical") or "").strip()
            if not abbrev or not entity or not value:
                continue
            db.add(
                Abbreviation(
                    abbreviation=abbrev,
                    entity=entity,
                    value=value,
                    description=(row.get("description") or "").strip() or None,
                    source="imported",
                    status="approved",
                )
            )
            applied += 1
        await db.commit()
        return {**preview, "applied": applied}

    async def _resolve_canonical(self, db: AsyncSession, canonical: str) -> GlossaryTerm:
        term = (
            await db.execute(
                select(GlossaryTerm)
                .options(selectinload(GlossaryTerm.synonyms))
                .where(GlossaryTerm.term.ilike(canonical))
            )
        ).scalar_one_or_none()
        if term:
            return term
        term = GlossaryTerm(term=canonical, definition=canonical, source="imported", status="approved")
        db.add(term)
        await db.flush()
        return term

    @staticmethod
    async def _resolve_table_id(db: AsyncSession, entity: str) -> str | None:
        if "." not in entity:
            return None
        db_name, table_name = entity.split(".", 1)
        table = (
            await db.execute(
                select(CatalogTable)
                .join(CatalogDatabase, CatalogTable.database_id == CatalogDatabase.id)
                .where(CatalogDatabase.name == db_name, CatalogTable.name == table_name)
            )
        ).scalar_one_or_none()
        return table.id if table else None


semantic_import_service = SemanticImportService()
