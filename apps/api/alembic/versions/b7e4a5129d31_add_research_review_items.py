"""add research review items

Revision ID: b7e4a5129d31
Revises: 7a6cb59e0d64
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e4a5129d31"
down_revision: Union[str, Sequence[str], None] = "7a6cb59e0d64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_review_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("research_run_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("next_action", sa.String(), nullable=True),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_review_items_research_run_id", "research_review_items", ["research_run_id"])
    op.create_index("ix_research_review_items_updated_by", "research_review_items", ["updated_by"])


def downgrade() -> None:
    op.drop_index("ix_research_review_items_updated_by", table_name="research_review_items")
    op.drop_index("ix_research_review_items_research_run_id", table_name="research_review_items")
    op.drop_table("research_review_items")
