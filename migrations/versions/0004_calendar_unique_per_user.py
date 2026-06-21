"""make calendar google_calendar_id unique per user

The literal "primary" identifies each user's own primary Google calendar, so a
global unique constraint on google_calendar_id breaks the moment a second user
connects. Replace it with a composite unique (user_id, google_calendar_id).

Revision ID: 0004_calendar_unique_per_user
Revises: 0003_google_credentials
"""
from alembic import op

revision = "0004_calendar_unique_per_user"
down_revision = "0003_google_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "calendars_google_calendar_id_key", "calendars", schema="simplificapsi", type_="unique"
    )
    op.create_unique_constraint(
        "uq_calendars_user_google_id",
        "calendars",
        ["user_id", "google_calendar_id"],
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_calendars_user_google_id", "calendars", schema="simplificapsi", type_="unique"
    )
    op.create_unique_constraint(
        "calendars_google_calendar_id_key",
        "calendars",
        ["google_calendar_id"],
        schema="simplificapsi",
    )
