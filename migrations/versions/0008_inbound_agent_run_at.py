"""add inbound_message.agent_run_at

Marks when the professional agent run for a message finished. NULL = not yet
run; the webhook opportunistically re-dispatches stale NULL rows (crash
recovery) without double-running (the marker is the idempotency guard).

Revision ID: 0008_inbound_agent_run_at
Revises: 0007_inbound_raw_jsonb
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_inbound_agent_run_at"
down_revision = "0007_inbound_raw_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_message",
        sa.Column("agent_run_at", sa.DateTime(timezone=True), nullable=True),
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_column("inbound_message", "agent_run_at", schema="simplificapsi")
