"""Add calculated_fields table: per-table virtual columns for SQL generation."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calculated_fields",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("table_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["table_id"], ["catalog_tables.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calculated_fields_table_id", "calculated_fields", ["table_id"])


def downgrade() -> None:
    op.drop_index("ix_calculated_fields_table_id", table_name="calculated_fields")
    op.drop_table("calculated_fields")
