"""CRUD for per-table calculated fields (virtual columns used in SQL generation)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, ValidationFailed
from app.models.catalog import CalculatedField, CatalogTable
from app.schemas.api import CalculatedFieldIn, CalculatedFieldOut, CalculatedFieldUpdate


def _to_out(row: CalculatedField) -> CalculatedFieldOut:
    return CalculatedFieldOut.model_validate(row)


async def list_for_table(db: AsyncSession, table_id: str) -> list[CalculatedFieldOut]:
    if not await db.get(CatalogTable, table_id):
        raise NotFound("Table not found")
    rows = (
        await db.execute(
            select(CalculatedField)
            .where(CalculatedField.table_id == table_id)
            .order_by(CalculatedField.created_at.desc())
        )
    ).scalars().all()
    return [_to_out(r) for r in rows]


async def create(db: AsyncSession, body: CalculatedFieldIn) -> CalculatedFieldOut:
    if not await db.get(CatalogTable, body.table_id):
        raise NotFound("Table not found")
    name = body.name.strip()
    expression = body.expression.strip()
    if not name:
        raise ValidationFailed("name must not be empty")
    if not expression:
        raise ValidationFailed("expression must not be empty")
    row = CalculatedField(
        table_id=body.table_id,
        name=name,
        expression=expression,
        description=(body.description or "").strip() or None,
        source="manual",
    )
    db.add(row)
    await db.flush()
    return _to_out(row)


async def update(db: AsyncSession, field_id: str, body: CalculatedFieldUpdate) -> CalculatedFieldOut:
    row = await db.get(CalculatedField, field_id)
    if not row:
        raise NotFound("Calculated field not found")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise ValidationFailed("name must not be empty")
        row.name = name
    if body.expression is not None:
        expression = body.expression.strip()
        if not expression:
            raise ValidationFailed("expression must not be empty")
        row.expression = expression
    if body.description is not None:
        row.description = body.description.strip() or None
    if body.is_active is not None:
        row.is_active = body.is_active
    return _to_out(row)


async def delete(db: AsyncSession, field_id: str) -> None:
    row = await db.get(CalculatedField, field_id)
    if not row:
        raise NotFound("Calculated field not found")
    await db.delete(row)
