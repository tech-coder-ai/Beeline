"""Add catalog_tables.sample_records for LLM SQL-gen grounding."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_tables",
        sa.Column("sample_records", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_tables", "sample_records")
