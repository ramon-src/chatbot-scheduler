"""make chat_sessions owner-agnostic (user OR lead)

Revision ID: 0013_chat_sessions_owner
Revises: 0012_leads
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_chat_sessions_owner"
down_revision = "0012_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "chat_sessions", "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True, schema="simplificapsi",
    )
    op.add_column(
        "chat_sessions",
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="simplificapsi",
    )
    op.create_foreign_key(
        "fk_chat_sessions_lead_id", "chat_sessions", "leads",
        ["lead_id"], ["id"],
        source_schema="simplificapsi", referent_schema="simplificapsi",
        ondelete="CASCADE",
    )
    op.create_index("ix_chat_sessions_lead_id", "chat_sessions", ["lead_id"], schema="simplificapsi")
    op.create_check_constraint(
        "ck_chat_sessions_one_owner", "chat_sessions",
        "(user_id IS NOT NULL) <> (lead_id IS NOT NULL)",
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_constraint("ck_chat_sessions_one_owner", "chat_sessions", schema="simplificapsi")
    op.drop_index("ix_chat_sessions_lead_id", table_name="chat_sessions", schema="simplificapsi")
    op.drop_constraint("fk_chat_sessions_lead_id", "chat_sessions", schema="simplificapsi", type_="foreignkey")
    op.drop_column("chat_sessions", "lead_id", schema="simplificapsi")
    op.alter_column(
        "chat_sessions", "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False, schema="simplificapsi",
    )
