"""add users.phone_normalized with a unique index

Materializes the normalized phone so a sender number resolves to at most one
professional. Backfills existing rows, then enforces uniqueness.

Revision ID: 0009_users_phone_normalized
Revises: 0008_inbound_agent_run_at
"""
import sqlalchemy as sa
from alembic import op

from app.channels.phone import normalize_phone

revision = "0009_users_phone_normalized"
down_revision = "0008_inbound_agent_run_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone_normalized", sa.String(length=20), nullable=True),
        schema="simplificapsi",
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, phone FROM simplificapsi.users WHERE phone IS NOT NULL")
    ).fetchall()
    for row_id, phone in rows:
        norm = normalize_phone(phone)
        if norm:
            conn.execute(
                sa.text("UPDATE simplificapsi.users SET phone_normalized = :n WHERE id = :i"),
                {"n": norm, "i": row_id},
            )
    op.create_index(
        "uq_users_phone_normalized", "users", ["phone_normalized"], unique=True,
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_index("uq_users_phone_normalized", table_name="users", schema="simplificapsi")
    op.drop_column("users", "phone_normalized", schema="simplificapsi")
