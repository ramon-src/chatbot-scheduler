"""create inbound_message table

Stores every received WhatsApp message (any provider) for idempotency, audit,
and as the lead queue for unlinked numbers.

Revision ID: 0006_inbound_message
Revises: 0005_chat_session_summary
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_inbound_message"
down_revision = "0005_chat_session_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("sender_phone", sa.String(length=20), nullable=False),
        sa.Column("recipient_phone", sa.String(length=20), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["simplificapsi.users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("provider", "provider_message_id", name="uq_inbound_provider_msg"),
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_inbound_message_provider", "inbound_message", ["provider"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_inbound_message_sender_phone", "inbound_message", ["sender_phone"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_inbound_message_classification", "inbound_message", ["classification"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_inbound_message_user_id", "inbound_message", ["user_id"],
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_table("inbound_message", schema="simplificapsi")
