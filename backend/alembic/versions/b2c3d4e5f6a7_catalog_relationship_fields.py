"""Add description, join_type, and composite column keys to catalog_relationships."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a0db532d69b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("catalog_relationships", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "catalog_relationships",
        sa.Column("join_type", sa.String(length=16), nullable=False, server_default="inner"),
    )
    op.add_column("catalog_relationships", sa.Column("from_columns", sa.JSON(), nullable=True))
    op.add_column("catalog_relationships", sa.Column("to_columns", sa.JSON(), nullable=True))
    op.execute(
        """
        UPDATE catalog_relationships
        SET from_columns = json_array(from_column),
            to_columns = json_array(to_column)
        WHERE from_columns IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("catalog_relationships", "to_columns")
    op.drop_column("catalog_relationships", "from_columns")
    op.drop_column("catalog_relationships", "join_type")
    op.drop_column("catalog_relationships", "description")
