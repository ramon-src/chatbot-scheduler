"""add occurrence + billable columns to events

Recurring sessions are materialized as per-occurrence rows (parent_event_id +
occurrence_date); billable records whether a session counts for billing.

Revision ID: 0010_event_occurrences
Revises: 0009_users_phone_normalized
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_event_occurrences"
down_revision = "0009_users_phone_normalized"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("parent_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="simplificapsi",
    )
    op.add_column(
        "events",
        sa.Column("occurrence_date", sa.Date(), nullable=True),
        schema="simplificapsi",
    )
    op.add_column(
        "events",
        sa.Column("billable", sa.Boolean(), server_default="true", nullable=False),
        schema="simplificapsi",
    )
    op.create_foreign_key(
        "fk_events_parent_event_id", "events", "events",
        ["parent_event_id"], ["id"],
        source_schema="simplificapsi", referent_schema="simplificapsi",
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_simplificapsi_events_parent_event_id", "events", ["parent_event_id"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_events_occurrence_date", "events", ["occurrence_date"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_events_billable", "events", ["billable"],
        schema="simplificapsi",
    )
    op.create_unique_constraint(
        "uq_event_occurrence", "events", ["parent_event_id", "occurrence_date"],
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_constraint("uq_event_occurrence", "events", schema="simplificapsi", type_="unique")
    op.drop_index("ix_simplificapsi_events_billable", table_name="events", schema="simplificapsi")
    op.drop_index("ix_simplificapsi_events_occurrence_date", table_name="events", schema="simplificapsi")
    op.drop_index("ix_simplificapsi_events_parent_event_id", table_name="events", schema="simplificapsi")
    op.drop_constraint("fk_events_parent_event_id", "events", schema="simplificapsi", type_="foreignkey")
    op.drop_column("events", "billable", schema="simplificapsi")
    op.drop_column("events", "occurrence_date", schema="simplificapsi")
    op.drop_column("events", "parent_event_id", schema="simplificapsi")
