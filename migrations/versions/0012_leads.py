"""create leads table (qualification funnel for unlinked WhatsApp numbers)

Revision ID: 0012_leads
Revises: 0011_user_access_expires
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_leads"
down_revision = "0011_user_access_expires"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="new", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("phone", name="uq_leads_phone"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["simplificapsi.users.id"], name="fk_leads_user_id", ondelete="SET NULL"
        ),
        schema="simplificapsi",
    )
    op.create_index("ix_leads_phone", "leads", ["phone"], schema="simplificapsi")
    op.create_index("ix_leads_status", "leads", ["status"], schema="simplificapsi")


def downgrade() -> None:
    op.drop_index("ix_leads_status", table_name="leads", schema="simplificapsi")
    op.drop_index("ix_leads_phone", table_name="leads", schema="simplificapsi")
    op.drop_table("leads", schema="simplificapsi")
