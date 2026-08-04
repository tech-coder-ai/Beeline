"""Abbreviation entity/value fields and catalog table canonical_name."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("abbreviations", sa.Column("entity", sa.String(length=512), nullable=True))
    op.add_column("abbreviations", sa.Column("value", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE abbreviations
        SET entity = COALESCE(entity, canonical),
            value = COALESCE(value, canonical)
        WHERE canonical IS NOT NULL
        """
    )
    with op.batch_alter_table("abbreviations") as batch:
        batch.drop_column("canonical")

    op.add_column(
        "catalog_tables",
        sa.Column("canonical_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_tables", "canonical_name")
    op.add_column("abbreviations", sa.Column("canonical", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE abbreviations
        SET canonical = COALESCE(value, entity)
        """
    )
    op.drop_column("abbreviations", "value")
    op.drop_column("abbreviations", "entity")
