"""Add business_rules table for conditional/policy business knowledge."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_rules",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="global"),
        sa.Column("entity", sa.String(length=512), nullable=True),
        sa.Column("column_name", sa.String(length=255), nullable=True),
        sa.Column("rule_type", sa.String(length=32), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="approved"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_business_rules_scope", "business_rules", ["scope"])
    op.create_index("ix_business_rules_entity", "business_rules", ["entity"])


def downgrade() -> None:
    op.drop_index("ix_business_rules_entity", table_name="business_rules")
    op.drop_index("ix_business_rules_scope", table_name="business_rules")
    op.drop_table("business_rules")
