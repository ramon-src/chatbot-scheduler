"""add client billing fields

Revision ID: 0002_client_billing_fields
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_client_billing_fields"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("invoice_day", sa.Integer(), nullable=True), schema="simplificapsi")
    op.add_column("clients", sa.Column("consult_price", sa.Numeric(10, 2), nullable=True), schema="simplificapsi")


def downgrade() -> None:
    op.drop_column("clients", "consult_price", schema="simplificapsi")
    op.drop_column("clients", "invoice_day", schema="simplificapsi")
