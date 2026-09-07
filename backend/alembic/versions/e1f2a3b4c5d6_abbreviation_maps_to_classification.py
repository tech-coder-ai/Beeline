"""Add abbreviations.maps_to_classification for explicit governance-concept mapping."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "abbreviations", sa.Column("maps_to_classification", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("abbreviations", "maps_to_classification")
