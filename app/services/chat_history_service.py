"""Conversation memory: persist and load chat turns scoped by (user, phone)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chat_session import ChatMessage, ChatSession


class ChatHistoryService:
    """Reads/writes the chat_sessions + chat_messages mirror.

    A conversation is scoped by (user_id, phone_number): the most recent active
    session for that pair is reused, otherwise a new one is created.
    """

    def __init__(self, db: Session, timezone: str | None = None):
        self.db = db
        self._tz = ZoneInfo(timezone or settings.TIMEZONE)

    def get_or_create_session(self, user_id: UUID, phone_number: str) -> ChatSession:
        existing = (
            self.db.query(ChatSession)
            .filter(
                and_(
                    ChatSession.user_id == user_id,
                    ChatSession.phone_number == phone_number,
                    ChatSession.is_active == True,  # noqa: E712
                )
            )
            .order_by(ChatSession.updated_at.desc())
            .first()
        )
        if existing is not None:
            return existing
        session = ChatSession(
            user_id=user_id,
            session_id=str(uuid.uuid4()),
            phone_number=phone_number,
            is_active=True,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_or_create_lead_session(self, lead_id: UUID, phone_number: str) -> ChatSession:
        existing = (
            self.db.query(ChatSession)
            .filter(
                and_(
                    ChatSession.lead_id == lead_id,
                    ChatSession.phone_number == phone_number,
                    ChatSession.is_active == True,  # noqa: E712
                )
            )
            .order_by(ChatSession.updated_at.desc())
            .first()
        )
        if existing is not None:
            return existing
        session = ChatSession(
            lead_id=lead_id,
            session_id=str(uuid.uuid4()),
            phone_number=phone_number,
            is_active=True,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def recent_messages(self, session: ChatSession, limit: int) -> list[ChatMessage]:
        """The most recent `limit` messages, in chronological (ascending) order.

        Secondary sort by id keeps a *total* order identical to
        `unsummarized_overflow`, so the kept-window and the summarized prefix stay
        aligned even if two rows share created_at.
        """
        rows = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(rows))

    def unsummarized_overflow(self, session: ChatSession, keep_recent: int) -> list[ChatMessage]:
        """Messages that fell out of the recent-`keep_recent` window and are not
        yet folded into the summary, oldest first.

        These are the only rows that need summarizing this turn — already-folded
        messages (tracked by `summarized_count`) are skipped, so cost stays bounded.

        `keep_recent` must be constant per session: the marker math assumes the
        kept window never shrinks/grows between turns (it is a module constant in
        the route). The id tiebreaker mirrors `recent_messages` so the offset
        window aligns exactly with the kept window.
        """
        total = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .count()
        )
        already = session.summarized_count or 0
        overflow = total - keep_recent - already
        if overflow <= 0:
            return []
        return (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .offset(already)
            .limit(overflow)
            .all()
        )

    def append_turn(self, session: ChatSession, user_text: str, assistant_text: str) -> None:
        """Persist one turn. created_at is set explicitly so the assistant row
        sorts strictly after the user row (server now() would tie them)."""
        now = datetime.now(self._tz)
        self.db.add(
            ChatMessage(
                session_id=session.id,
                message_type="user",
                content=user_text,
                created_at=now,
            )
        )
        self.db.add(
            ChatMessage(
                session_id=session.id,
                message_type="assistant",
                content=assistant_text,
                created_at=now + timedelta(microseconds=1),
            )
        )
        session.updated_at = now
        self.db.commit()

    def fold_summary(self, session: ChatSession, summary: str, summarized_count: int) -> None:
        """Store the new rolling summary and advance the folded-message marker."""
        session.summary = summary
        session.summarized_count = summarized_count
        self.db.commit()
