"""add rolling summary columns to chat_sessions

Conversation memory keeps the most recent turns raw and folds older turns into
a rolling text summary injected via the system prompt. `summarized_count` tracks
how many messages have already been folded, so each turn only summarizes the new
overflow (bounded cost) instead of re-reading the whole history.

Revision ID: 0005_chat_session_summary
Revises: 0004_calendar_unique_per_user
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_chat_session_summary"
down_revision = "0004_calendar_unique_per_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("summary", sa.Text(), nullable=True),
        schema="simplificapsi",
    )
    op.add_column(
        "chat_sessions",
        sa.Column(
            "summarized_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "summarized_count", schema="simplificapsi")
    op.drop_column("chat_sessions", "summary", schema="simplificapsi")
