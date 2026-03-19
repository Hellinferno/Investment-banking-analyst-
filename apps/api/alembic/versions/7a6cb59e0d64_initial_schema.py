"""initial_schema

Revision ID: 7a6cb59e0d64
Revises:
Create Date: 2026-03-15 19:41:37.299366

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7a6cb59e0d64'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deals',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True, index=True),
        sa.Column('owner_id', sa.String(), nullable=True, index=True),
        sa.Column('name', sa.String(), nullable=True, index=True),
        sa.Column('company_name', sa.String(), nullable=True, index=True),
        sa.Column('deal_type', sa.String(), nullable=True),
        sa.Column('industry', sa.String(), nullable=True),
        sa.Column('deal_stage', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'documents',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('deal_id', sa.String(), nullable=True),
        sa.Column('filename', sa.String(), nullable=True),
        sa.Column('file_type', sa.String(), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('storage_path', sa.String(), nullable=True),
        sa.Column('doc_category', sa.String(), nullable=True),
        sa.Column('is_mnpi', sa.Boolean(), nullable=True, default=False),
        sa.Column('mnpi_consent_given', sa.Boolean(), nullable=True, default=False),
        sa.Column('parsed_text', sa.String(), nullable=True),
        sa.Column('parse_status', sa.String(), nullable=True),
        sa.Column('rag_status', sa.String(), nullable=True, default='pending'),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'agent_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('deal_id', sa.String(), nullable=True),
        sa.Column('agent_type', sa.String(), nullable=True),
        sa.Column('task_name', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('input_payload', sa.JSON(), nullable=True),
        sa.Column('reasoning_steps', sa.JSON(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'outputs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('deal_id', sa.String(), nullable=True),
        sa.Column('agent_run_id', sa.String(), nullable=True),
        sa.Column('filename', sa.String(), nullable=True),
        sa.Column('output_type', sa.String(), nullable=True),
        sa.Column('output_category', sa.String(), nullable=True),
        sa.Column('storage_path', sa.String(), nullable=True),
        sa.Column('review_status', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'extraction_audits',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('deal_id', sa.String(), nullable=True),
        sa.Column('agent_run_id', sa.String(), nullable=True),
        sa.Column('field_name', sa.String(), nullable=True),
        sa.Column('extracted_value', sa.JSON(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('source_citation', sa.String(), nullable=True),
        sa.Column('reasoning', sa.String(), nullable=True),
        sa.Column('auditor_status', sa.String(), nullable=True),
        sa.Column('auditor_confidence', sa.Float(), nullable=True),
        sa.Column('auditor_reason', sa.String(), nullable=True),
        sa.Column('triangulation_status', sa.String(), nullable=True),
        sa.Column('triangulation_details', sa.String(), nullable=True),
        sa.Column('user_override', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'tasks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('deal_id', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('priority', sa.String(), nullable=True),
        sa.Column('owner', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_ai_generated', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'output_review_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('output_id', sa.String(), nullable=True, index=True),
        sa.Column('reviewer_id', sa.String(), nullable=True, index=True),
        sa.Column('review_status', sa.String(), nullable=True),
        sa.Column('reviewer_notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['output_id'], ['outputs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'security_audit_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True, index=True),
        sa.Column('user_id', sa.String(), nullable=True, index=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('resource_type', sa.String(), nullable=True),
        sa.Column('resource_id', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('request_id', sa.String(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('integrity_hash', sa.String(), nullable=True),
        sa.Column('prev_hash', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'webhooks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True, index=True),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('secret', sa.String(), nullable=True),
        sa.Column('event_types', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('webhooks')
    op.drop_table('security_audit_log')
    op.drop_table('output_review_events')
    op.drop_table('tasks')
    op.drop_table('extraction_audits')
    op.drop_table('outputs')
    op.drop_table('agent_runs')
    op.drop_table('documents')
    op.drop_table('deals')
