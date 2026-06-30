"""client billing_mode

Revision ID: 0014_client_billing_mode
Revises: 0013_chat_sessions_owner
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_client_billing_mode"
down_revision = "0013_chat_sessions_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("billing_mode", sa.String(length=20), nullable=False, server_default="monthly"),
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_column("clients", "billing_mode", schema="simplificapsi")
