"""add google_credentials table

Revision ID: 0003_google_credentials
Revises: 0002_client_billing_fields
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_google_credentials"
down_revision = "0002_client_billing_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("token_uri", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["simplificapsi.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_google_credentials_user_id"),
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_google_credentials_user_id",
        "google_credentials",
        ["user_id"],
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_simplificapsi_google_credentials_user_id",
        table_name="google_credentials",
        schema="simplificapsi",
    )
    op.drop_table("google_credentials", schema="simplificapsi")
