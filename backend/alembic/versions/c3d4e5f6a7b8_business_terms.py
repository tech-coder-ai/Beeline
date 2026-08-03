"""Add business_terms table for term-to-column value mappings."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_terms",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("entity", sa.String(length=512), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("table_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="approved"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["table_id"], ["catalog_tables.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_business_terms_term", "business_terms", ["term"])
    op.create_index("ix_business_terms_entity", "business_terms", ["entity"])


def downgrade() -> None:
    op.drop_index("ix_business_terms_entity", table_name="business_terms")
    op.drop_index("ix_business_terms_term", table_name="business_terms")
    op.drop_table("business_terms")
