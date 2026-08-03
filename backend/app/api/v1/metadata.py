"""Metadata API: catalog browsing/editing, glossary, approvals, import."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.exceptions import NotFound, ValidationFailed
from app.models.catalog import CatalogColumn, CatalogDatabase, CatalogTable
from app.models.semantic import Abbreviation, BusinessMetric, BusinessTerm, GlossaryTerm, Synonym
from app.schemas.api import (
    AbbreviationIn,
    AbbreviationOut,
    ApprovalDecision,
    ApprovalOut,
    BulkApprovalDecision,
    BusinessTermIn,
    BusinessTermOut,
    ColumnUpdate,
    GlossaryTermIn,
    GlossaryTermOut,
    RelationshipIn,
    RelationshipOut,
    RelationshipUpdate,
    TableDetailOut,
    TableEnrichRequest,
    TableOut,
    TableUpdate,
)
from app.services.approval import approval_service
from app.services.audit import audit
from app.services.catalog_relationships import create as create_relationship
from app.services.catalog_relationships import delete as delete_relationship
from app.services.catalog_relationships import list_for_table as list_relationships
from app.services.catalog_relationships import update as update_relationship
from app.services.enrichment import enrichment_service
from app.services.semantic_import import semantic_import_service

router = APIRouter(prefix="/metadata", tags=["metadata"])
glossary_router = APIRouter(prefix="/glossary", tags=["glossary"])
business_terms_router = APIRouter(prefix="/business-terms", tags=["business-terms"])
abbreviations_router = APIRouter(prefix="/abbreviations", tags=["abbreviations"])


# ------------------------------------------------------------------ catalog
@router.get("/databases")
async def list_databases(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(CatalogDatabase, func.count(CatalogTable.id))
            .outerjoin(CatalogTable, CatalogTable.database_id == CatalogDatabase.id)
            .group_by(CatalogDatabase.id)
            .order_by(CatalogDatabase.name)
        )
    ).all()
    return [
        {
            "id": d.id, "name": d.name, "connector_id": d.connector_id,
            "table_count": count, "last_synced_at": d.last_synced_at,
        }
        for d, count in rows
    ]


@router.get("/tables", response_model=list[TableOut])
async def list_tables(database_id: str | None = None, search: str | None = None,
                      db: AsyncSession = Depends(get_db)):
    stmt = (
        select(CatalogTable, CatalogDatabase.name, func.count(CatalogColumn.id))
        .join(CatalogDatabase, CatalogTable.database_id == CatalogDatabase.id)
        .outerjoin(CatalogColumn, CatalogColumn.table_id == CatalogTable.id)
        .where(CatalogTable.is_active.is_(True))
        .group_by(CatalogTable.id, CatalogDatabase.name)
        .order_by(CatalogTable.usage_count.desc(), CatalogTable.name)
    )
    if database_id:
        stmt = stmt.where(CatalogTable.database_id == database_id)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            CatalogTable.name.ilike(pattern) | CatalogTable.description.ilike(pattern)
        )
    rows = (await db.execute(stmt)).all()
    return [
        TableOut(**{
            **{c: getattr(t, c) for c in (
                "id", "name", "table_type", "description", "owner", "steward", "tags",
                "classification", "row_count", "size_bytes", "storage_format",
                "partition_columns", "last_synced_at", "usage_count",
            )},
            "database_name": db_name, "column_count": col_count,
        })
        for t, db_name, col_count in rows
    ]


@router.get("/tables/{table_id}", response_model=TableDetailOut)
async def get_table(table_id: str, db: AsyncSession = Depends(get_db)):
    table = (
        await db.execute(
            select(CatalogTable)
            .options(selectinload(CatalogTable.columns), selectinload(CatalogTable.database))
            .where(CatalogTable.id == table_id)
        )
    ).scalar_one_or_none()
    if not table:
        raise NotFound("Table not found")
    return TableDetailOut(
        **{c: getattr(table, c) for c in (
            "id", "name", "table_type", "description", "owner", "steward", "tags",
            "classification", "row_count", "size_bytes", "storage_format",
            "partition_columns", "last_synced_at", "usage_count",
        )},
        database_name=table.database.name,
        column_count=len(table.columns),
        columns=[
            {c: getattr(col, c) for c in (
                "id", "name", "position", "data_type", "inferred_semantic_type", "description",
                "tags", "classification", "is_pii", "is_partition", "null_percentage",
                "distinct_count", "sample_values", "top_values",
            )}
            for col in table.columns
        ],
    )


@router.patch("/tables/{table_id}")
async def update_table(table_id: str, update: TableUpdate, db: AsyncSession = Depends(get_db)):
    table = await db.get(CatalogTable, table_id)
    if not table:
        raise NotFound("Table not found")
    for key, value in update.model_dump(exclude_none=True).items():
        setattr(table, key, value)
    await audit(db, "default", "metadata.edit", entity_type="table", entity_id=table_id)
    await db.commit()
    return {"updated": table_id}


@router.post("/tables/{table_id}/enrich")
async def enrich_table(
    table_id: str,
    request: TableEnrichRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    result = await enrichment_service.enrich_table(db, table_id, request)
    await audit(db, "default", "metadata.enrich", entity_type="table", entity_id=table_id, detail=result)
    await db.commit()
    return result


@router.get("/relationships", response_model=list[RelationshipOut])
async def list_table_relationships(table_id: str, db: AsyncSession = Depends(get_db)):
    return await list_relationships(db, table_id)


@router.post("/relationships", response_model=RelationshipOut)
async def create_table_relationship(body: RelationshipIn, db: AsyncSession = Depends(get_db)):
    out = await create_relationship(db, body)
    await audit(
        db,
        "default",
        "metadata.relationship.create",
        entity_type="relationship",
        entity_id=out.id,
        detail={"from": out.from_table_id, "to": out.to_table_id},
    )
    await db.commit()
    return out


@router.patch("/relationships/{relationship_id}", response_model=RelationshipOut)
async def patch_table_relationship(
    relationship_id: str, body: RelationshipUpdate, db: AsyncSession = Depends(get_db)
):
    out = await update_relationship(db, relationship_id, body)
    await audit(db, "default", "metadata.relationship.update", entity_type="relationship", entity_id=relationship_id)
    await db.commit()
    return out


@router.delete("/relationships/{relationship_id}")
async def remove_table_relationship(relationship_id: str, db: AsyncSession = Depends(get_db)):
    await delete_relationship(db, relationship_id)
    await audit(db, "default", "metadata.relationship.delete", entity_type="relationship", entity_id=relationship_id)
    await db.commit()
    return {"deleted": relationship_id}


@router.patch("/columns/{column_id}")
async def update_column(column_id: str, update: ColumnUpdate, db: AsyncSession = Depends(get_db)):
    column = await db.get(CatalogColumn, column_id)
    if not column:
        raise NotFound("Column not found")
    for key, value in update.model_dump(exclude_none=True).items():
        setattr(column, key, value)
    await audit(db, "default", "metadata.edit", entity_type="column", entity_id=column_id)
    await db.commit()
    return {"updated": column_id}


# ------------------------------------------------------------------ approvals
@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(entity_type: str | None = None, status: str = "pending",
                         db: AsyncSession = Depends(get_db)):
    return await approval_service.list_pending(db, entity_type, status)


@router.get("/approvals/counts")
async def approval_counts(db: AsyncSession = Depends(get_db)):
    return await approval_service.counts(db)


@router.post("/approvals/{item_id}", response_model=ApprovalOut)
async def decide_approval(item_id: str, decision: ApprovalDecision,
                          db: AsyncSession = Depends(get_db)):
    item = await approval_service.decide(
        db, item_id, decision.action, decision.edited_value, decision.note
    )
    await db.commit()
    return item


@router.post("/approvals/bulk/decide")
async def bulk_decide(decision: BulkApprovalDecision, db: AsyncSession = Depends(get_db)):
    result = await approval_service.bulk_decide(db, decision.ids, decision.action, decision.note)
    await db.commit()
    return result


@router.get("/versions/{entity_type}/{entity_id}")
async def version_history(entity_type: str, entity_id: str, db: AsyncSession = Depends(get_db)):
    versions = await approval_service.history(db, entity_type, entity_id)
    return [
        {c: getattr(v, c) for c in (
            "id", "field", "old_value", "new_value", "version",
            "changed_by", "change_source", "created_at",
        )}
        for v in versions
    ]


@router.post("/versions/{version_id}/rollback")
async def rollback_version(version_id: str, db: AsyncSession = Depends(get_db)):
    await approval_service.rollback(db, version_id)
    await db.commit()
    return {"rolled_back": version_id}


# ------------------------------------------------------------------ import
@router.post("/import/preview")
async def import_preview(
    file: UploadFile,
    import_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    rows = semantic_import_service.parse(file.filename or "upload.csv", await file.read())
    return await semantic_import_service.preview(db, rows, import_type)


@router.post("/import/commit")
async def import_commit(
    file: UploadFile,
    import_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    rows = semantic_import_service.parse(file.filename or "upload.csv", await file.read())
    result = await semantic_import_service.commit(db, rows, import_type)
    await audit(db, "default", "metadata.import", detail={"import_type": result.get("import_type")})
    await db.commit()
    return result


# ------------------------------------------------------------------ glossary
@glossary_router.get("", response_model=list[GlossaryTermOut])
async def list_terms(search: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(GlossaryTerm).options(selectinload(GlossaryTerm.synonyms)).order_by(GlossaryTerm.term)
    if search:
        stmt = stmt.where(GlossaryTerm.term.ilike(f"%{search}%"))
    terms = (await db.execute(stmt)).scalars().all()
    return [
        GlossaryTermOut(
            id=t.id, term=t.term, definition=t.definition, business_meaning=t.business_meaning,
            examples=t.examples or [], owner=t.owner, tags=t.tags or [],
            synonyms=[s.synonym for s in t.synonyms], status=t.status, source=t.source,
            created_at=t.created_at,
        )
        for t in terms
    ]


@glossary_router.post("", response_model=GlossaryTermOut)
async def create_term(term_in: GlossaryTermIn, db: AsyncSession = Depends(get_db)):
    term = GlossaryTerm(
        term=term_in.term, definition=term_in.definition,
        business_meaning=term_in.business_meaning, examples=term_in.examples,
        owner=term_in.owner, tags=term_in.tags, source="manual", status="approved",
    )
    db.add(term)
    await db.flush()
    for synonym in term_in.synonyms:
        db.add(Synonym(term_id=term.id, synonym=synonym))
    await db.commit()
    return GlossaryTermOut(
        id=term.id, term=term.term, definition=term.definition,
        business_meaning=term.business_meaning, examples=term.examples or [],
        owner=term.owner, tags=term.tags or [], synonyms=term_in.synonyms,
        status=term.status, source=term.source, created_at=term.created_at,
    )


@glossary_router.put("/{term_id}", response_model=GlossaryTermOut)
async def update_term(term_id: str, term_in: GlossaryTermIn, db: AsyncSession = Depends(get_db)):
    term = (
        await db.execute(
            select(GlossaryTerm).options(selectinload(GlossaryTerm.synonyms))
            .where(GlossaryTerm.id == term_id)
        )
    ).scalar_one_or_none()
    if not term:
        raise NotFound("Glossary term not found")
    term.term = term_in.term
    term.definition = term_in.definition
    term.business_meaning = term_in.business_meaning
    term.examples = term_in.examples
    term.owner = term_in.owner
    term.tags = term_in.tags
    for s in list(term.synonyms):
        await db.delete(s)
    await db.flush()
    for synonym in term_in.synonyms:
        db.add(Synonym(term_id=term.id, synonym=synonym))
    await db.commit()
    return GlossaryTermOut(
        id=term.id, term=term.term, definition=term.definition,
        business_meaning=term.business_meaning, examples=term.examples or [],
        owner=term.owner, tags=term.tags or [], synonyms=term_in.synonyms,
        status=term.status, source=term.source, created_at=term.created_at,
    )


@glossary_router.delete("/{term_id}")
async def delete_term(term_id: str, db: AsyncSession = Depends(get_db)):
    term = await db.get(GlossaryTerm, term_id)
    if not term:
        raise NotFound("Glossary term not found")
    await db.delete(term)
    await db.commit()
    return {"deleted": term_id}


@glossary_router.get("/metrics")
async def list_metrics(db: AsyncSession = Depends(get_db)):
    metrics = (await db.execute(select(BusinessMetric).order_by(BusinessMetric.name))).scalars().all()
    return [
        {c: getattr(m, c) for c in (
            "id", "name", "description", "expression", "table_qualified_name",
            "unit", "aggregation", "is_kpi", "tags", "status",
        )}
        for m in metrics
    ]


async def _resolve_business_entity(db: AsyncSession, entity: str | None, table_id: str | None) -> str:
    if entity and entity.strip():
        return entity.strip()
    if not table_id:
        raise ValidationFailed("entity or table_id is required")
    table = await db.get(CatalogTable, table_id)
    if not table:
        raise NotFound("Table not found")
    db_row = await db.get(CatalogDatabase, table.database_id)
    db_name = db_row.name if db_row else ""
    return f"{db_name}.{table.name}"


def _business_term_out(row: BusinessTerm) -> BusinessTermOut:
    return BusinessTermOut(
        id=row.id,
        term=row.term,
        entity=row.entity,
        column_name=row.column_name,
        value=row.value,
        table_id=row.table_id,
        status=row.status,
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@business_terms_router.get("", response_model=list[BusinessTermOut])
async def list_business_terms(
    search: str | None = None,
    entity: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BusinessTerm).order_by(BusinessTerm.term)
    if search:
        stmt = stmt.where(BusinessTerm.term.ilike(f"%{search}%"))
    if entity:
        stmt = stmt.where(BusinessTerm.entity.ilike(f"%{entity}%"))
    rows = (await db.execute(stmt)).scalars().all()
    return [_business_term_out(r) for r in rows]


@business_terms_router.post("", response_model=BusinessTermOut)
async def create_business_term(body: BusinessTermIn, db: AsyncSession = Depends(get_db)):
    resolved_entity = await _resolve_business_entity(db, body.entity, body.table_id)
    row = BusinessTerm(
        term=body.term.strip(),
        entity=resolved_entity,
        column_name=body.column_name.strip(),
        value=body.value.strip(),
        table_id=body.table_id,
        source="manual",
        status="approved",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await audit(db, "default", "business_term.create", entity_type="business_term", entity_id=row.id)
    await db.commit()
    return _business_term_out(row)


@business_terms_router.put("/{term_id}", response_model=BusinessTermOut)
async def update_business_term(term_id: str, body: BusinessTermIn, db: AsyncSession = Depends(get_db)):
    row = await db.get(BusinessTerm, term_id)
    if not row:
        raise NotFound("Business term not found")
    row.term = body.term.strip()
    row.entity = await _resolve_business_entity(db, body.entity, body.table_id)
    row.column_name = body.column_name.strip()
    row.value = body.value.strip()
    row.table_id = body.table_id
    await db.commit()
    await db.refresh(row)
    await audit(db, "default", "business_term.update", entity_type="business_term", entity_id=term_id)
    await db.commit()
    return _business_term_out(row)


@business_terms_router.delete("/{term_id}")
async def delete_business_term(term_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(BusinessTerm, term_id)
    if not row:
        raise NotFound("Business term not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": term_id}


def _abbreviation_out(row: Abbreviation) -> AbbreviationOut:
    return AbbreviationOut(
        id=row.id,
        abbreviation=row.abbreviation,
        canonical=row.canonical,
        description=row.description,
        status=row.status,
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@abbreviations_router.get("", response_model=list[AbbreviationOut])
async def list_abbreviations(search: str | None = None, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Abbreviation).order_by(Abbreviation.abbreviation))).scalars().all()
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in r.abbreviation.lower() or needle in r.canonical.lower()]
    return [_abbreviation_out(r) for r in rows]


@abbreviations_router.post("", response_model=AbbreviationOut)
async def create_abbreviation(body: AbbreviationIn, db: AsyncSession = Depends(get_db)):
    row = Abbreviation(
        abbreviation=body.abbreviation.strip(),
        canonical=body.canonical.strip(),
        description=body.description,
        source="manual",
        status="approved",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _abbreviation_out(row)


@abbreviations_router.put("/{abbreviation_id}", response_model=AbbreviationOut)
async def update_abbreviation(abbreviation_id: str, body: AbbreviationIn, db: AsyncSession = Depends(get_db)):
    row = await db.get(Abbreviation, abbreviation_id)
    if not row:
        raise NotFound("Abbreviation not found")
    row.abbreviation = body.abbreviation.strip()
    row.canonical = body.canonical.strip()
    row.description = body.description
    await db.commit()
    await db.refresh(row)
    return _abbreviation_out(row)


@abbreviations_router.delete("/{abbreviation_id}")
async def delete_abbreviation(abbreviation_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Abbreviation, abbreviation_id)
    if not row:
        raise NotFound("Abbreviation not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": abbreviation_id}
