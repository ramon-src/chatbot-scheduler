"""add access_expires_at to users (trial expiry for lead-created accounts)

Revision ID: 0011_user_access_expires
Revises: 0010_event_occurrences
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_user_access_expires"
down_revision = "0010_event_occurrences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_column("users", "access_expires_at", schema="simplificapsi")
