"""Add abbreviations table."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abbreviations",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("abbreviation", sa.String(length=64), nullable=False),
        sa.Column("canonical", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="approved"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abbreviations_abbreviation", "abbreviations", ["abbreviation"])


def downgrade() -> None:
    op.drop_index("ix_abbreviations_abbreviation", table_name="abbreviations")
    op.drop_table("abbreviations")
