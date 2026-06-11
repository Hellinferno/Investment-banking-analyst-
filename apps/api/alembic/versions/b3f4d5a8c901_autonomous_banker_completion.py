"""autonomous_banker_completion

Revision ID: b3f4d5a8c901
Revises: 7a6cb59e0d64
Create Date: 2026-06-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3f4d5a8c901"
down_revision: Union[str, Sequence[str], None] = "7a6cb59e0d64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _add_column_if_missing(inspector, table_name: str, column: sa.Column) -> None:
    if not _has_column(inspector, table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _add_column_if_missing(inspector, "deals", sa.Column("process_stage", sa.String(), nullable=True))
    _add_column_if_missing(inspector, "deals", sa.Column("stage_last_updated", sa.DateTime(), nullable=True))

    for col in (
        sa.Column("model_provider", sa.String(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("validator_status", sa.String(), nullable=True),
        sa.Column("validator_report", sa.JSON(), nullable=True),
        sa.Column("checkpoint_status", sa.String(), nullable=True),
    ):
        _add_column_if_missing(inspector, "agent_runs", col)

    for col in (
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.String(), nullable=True),
    ):
        _add_column_if_missing(inspector, "outputs", col)

    if not _has_table(inspector, "buyer_outreach"):
        op.create_table(
            "buyer_outreach",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("deal_id", sa.String(), nullable=True),
            sa.Column("buyer_idx", sa.Integer(), nullable=False),
            sa.Column("buyer_name", sa.String(), nullable=False),
            sa.Column("buyer_type", sa.String(), nullable=True),
            sa.Column("outreach_status", sa.String(), nullable=True),
            sa.Column("source_run_id", sa.String(), nullable=True),
            sa.Column("buyer_payload", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_buyer_outreach_deal_id", "buyer_outreach", ["deal_id"])

    if not _has_table(inspector, "model_registry"):
        op.create_table(
            "model_registry",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("tenant_id", sa.String(), nullable=True),
            sa.Column("purpose", sa.String(), nullable=False),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("model_name", sa.String(), nullable=False),
            sa.Column("prompt_version", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("config", sa.JSON(), nullable=True),
            sa.Column("validation_status", sa.String(), nullable=True),
            sa.Column("validation_report", sa.JSON(), nullable=True),
            sa.Column("rollback_from_id", sa.String(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("promoted_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_model_registry_tenant_id", "model_registry", ["tenant_id"])
        op.create_index("ix_model_registry_purpose", "model_registry", ["purpose"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "buyer_outreach"):
        op.drop_index("ix_buyer_outreach_deal_id", table_name="buyer_outreach")
        op.drop_table("buyer_outreach")

    if _has_table(inspector, "model_registry"):
        op.drop_index("ix_model_registry_purpose", table_name="model_registry")
        op.drop_index("ix_model_registry_tenant_id", table_name="model_registry")
        op.drop_table("model_registry")

    for table_name, column_names in {
        "outputs": ["review_comment", "reviewed_at", "reviewed_by"],
        "agent_runs": [
            "checkpoint_status",
            "validator_report",
            "validator_status",
            "prompt_version",
            "model_name",
            "model_provider",
        ],
        "deals": ["stage_last_updated", "process_stage"],
    }.items():
        for column_name in column_names:
            if _has_column(inspector, table_name, column_name):
                op.drop_column(table_name, column_name)
