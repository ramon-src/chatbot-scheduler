"""alter inbound_message.raw from JSON to JSONB

JSONB lets us index/query the audit payload later; JSON was write-only.

Revision ID: 0007_inbound_raw_jsonb
Revises: 0006_inbound_message
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_inbound_raw_jsonb"
down_revision = "0006_inbound_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "inbound_message",
        "raw",
        type_=postgresql.JSONB(),
        postgresql_using="raw::jsonb",
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.alter_column(
        "inbound_message",
        "raw",
        type_=sa.JSON(),
        postgresql_using="raw::json",
        schema="simplificapsi",
    )
