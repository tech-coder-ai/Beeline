"""CRUD for declared catalog table relationships."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, ValidationFailed
from app.models.catalog import CatalogColumn, CatalogDatabase, CatalogRelationship, CatalogTable
from app.schemas.api import RelationshipIn, RelationshipOut, RelationshipUpdate

CARDINALITIES = {"many_to_one", "one_to_many", "one_to_one", "many_to_many"}
JOIN_TYPES = {"inner", "left", "right", "full"}


def _column_list(raw: list | None, fallback: str | None) -> list[str]:
    if raw:
        return [str(c) for c in raw if str(c).strip()]
    return [fallback] if fallback else []


async def _validate_columns(db: AsyncSession, table_id: str, cols: list[str], label: str) -> list[str]:
    if not cols:
        raise ValidationFailed(f"{label}_columns must not be empty")
    valid = {
        c.name.lower()
        for c in (
            await db.execute(select(CatalogColumn).where(CatalogColumn.table_id == table_id))
        ).scalars().all()
    }
    out: list[str] = []
    for col in cols:
        trimmed = col.strip()
        if not trimmed:
            continue
        if trimmed.lower() not in valid:
            raise ValidationFailed(f"Unknown {label} column: {trimmed}")
        out.append(trimmed)
    if not out:
        raise ValidationFailed(f"{label}_columns must not be empty")
    return out


def _apply_columns(rel: CatalogRelationship, from_cols: list[str], to_cols: list[str]) -> None:
    rel.from_columns = from_cols
    rel.to_columns = to_cols
    rel.from_column = from_cols[0]
    rel.to_column = to_cols[0]


async def _to_out(db: AsyncSession, rel: CatalogRelationship) -> RelationshipOut:
    from_table = await db.get(CatalogTable, rel.from_table_id)
    to_table = await db.get(CatalogTable, rel.to_table_id)
    if not from_table or not to_table:
        raise NotFound("Relationship table not found")
    from_db = await db.get(CatalogDatabase, from_table.database_id)
    to_db = await db.get(CatalogDatabase, to_table.database_id)
    return RelationshipOut(
        id=rel.id,
        from_table_id=rel.from_table_id,
        from_table_name=from_table.name,
        from_database_name=from_db.name if from_db else "",
        to_table_id=rel.to_table_id,
        to_table_name=to_table.name,
        to_database_name=to_db.name if to_db else "",
        from_columns=_column_list(rel.from_columns, rel.from_column),
        to_columns=_column_list(rel.to_columns, rel.to_column),
        relationship_type=rel.relationship_type,
        join_type=rel.join_type,
        description=rel.description,
        source=rel.source,
        confidence=rel.confidence,
        is_approved=rel.is_approved,
        created_at=rel.created_at,
        updated_at=rel.updated_at,
    )


async def list_for_table(db: AsyncSession, table_id: str) -> list[RelationshipOut]:
    if not await db.get(CatalogTable, table_id):
        raise NotFound("Table not found")
    rows = (
        await db.execute(
            select(CatalogRelationship)
            .where(
                (CatalogRelationship.from_table_id == table_id)
                | (CatalogRelationship.to_table_id == table_id)
            )
            .order_by(CatalogRelationship.created_at.desc())
        )
    ).scalars().all()
    return [await _to_out(db, r) for r in rows]


async def create(db: AsyncSession, body: RelationshipIn) -> RelationshipOut:
    if not await db.get(CatalogTable, body.from_table_id):
        raise NotFound("From table not found")
    if not await db.get(CatalogTable, body.to_table_id):
        raise NotFound("To table not found")
    from_cols = await _validate_columns(db, body.from_table_id, body.from_columns, "from")
    to_cols = await _validate_columns(db, body.to_table_id, body.to_columns, "to")
    if len(from_cols) != len(to_cols):
        raise ValidationFailed("from_columns and to_columns must have the same length")
    rel_type = (body.relationship_type or "many_to_one").lower()
    join_type = (body.join_type or "inner").lower()
    if rel_type not in CARDINALITIES:
        raise ValidationFailed(f"relationship_type must be one of: {sorted(CARDINALITIES)}")
    if join_type not in JOIN_TYPES:
        raise ValidationFailed(f"join_type must be one of: {sorted(JOIN_TYPES)}")

    rel = CatalogRelationship(
        from_table_id=body.from_table_id,
        to_table_id=body.to_table_id,
        relationship_type=rel_type,
        join_type=join_type,
        description=(body.description or "").strip() or None,
        source="manual",
        is_approved=True if body.is_approved is None else body.is_approved,
    )
    _apply_columns(rel, from_cols, to_cols)
    db.add(rel)
    await db.flush()
    return await _to_out(db, rel)


async def update(db: AsyncSession, relationship_id: str, body: RelationshipUpdate) -> RelationshipOut:
    rel = await db.get(CatalogRelationship, relationship_id)
    if not rel:
        raise NotFound("Relationship not found")
    from_cols = (
        await _validate_columns(db, rel.from_table_id, body.from_columns, "from")
        if body.from_columns is not None
        else _column_list(rel.from_columns, rel.from_column)
    )
    to_cols = (
        await _validate_columns(db, rel.to_table_id, body.to_columns, "to")
        if body.to_columns is not None
        else _column_list(rel.to_columns, rel.to_column)
    )
    if body.from_columns is not None or body.to_columns is not None:
        if len(from_cols) != len(to_cols):
            raise ValidationFailed("from_columns and to_columns must have the same length")
        _apply_columns(rel, from_cols, to_cols)
    if body.relationship_type is not None:
        rel_type = body.relationship_type.lower()
        if rel_type not in CARDINALITIES:
            raise ValidationFailed(f"relationship_type must be one of: {sorted(CARDINALITIES)}")
        rel.relationship_type = rel_type
    if body.join_type is not None:
        jt = body.join_type.lower()
        if jt not in JOIN_TYPES:
            raise ValidationFailed(f"join_type must be one of: {sorted(JOIN_TYPES)}")
        rel.join_type = jt
    if body.description is not None:
        rel.description = body.description.strip() or None
    if body.is_approved is not None:
        rel.is_approved = body.is_approved
    return await _to_out(db, rel)


async def delete(db: AsyncSession, relationship_id: str) -> None:
    rel = await db.get(CatalogRelationship, relationship_id)
    if not rel:
        raise NotFound("Relationship not found")
    await db.delete(rel)


def format_for_planner(table_names: dict[str, str], rows: list[CatalogRelationship]) -> str:
    lines: list[str] = []
    for r in rows:
        from_q = table_names.get(r.from_table_id)
        to_q = table_names.get(r.to_table_id)
        if not from_q or not to_q:
            continue
        from_cols = _column_list(r.from_columns, r.from_column)
        to_cols = _column_list(r.to_columns, r.to_column)
        keys = " AND ".join(
            f"{from_q}.{fc} = {to_q}.{tc}" for fc, tc in zip(from_cols, to_cols, strict=False)
        )
        line = f"{from_q} -> {to_q}: {keys} [{r.relationship_type}, {r.join_type} join"
        if r.description:
            line += f"; {r.description.strip()}"
        line += "]"
        lines.append(line)
    return "\n".join(lines)
