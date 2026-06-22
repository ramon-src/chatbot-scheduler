"""Resolve an inbound sender phone to a registered professional (User)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.channels.phone import normalize_phone
from app.models.user import User


def resolve_sender(db: Session, phone: str) -> User | None:
    target = normalize_phone(phone)
    if not target:
        return None
    return (
        db.query(User)
        .filter(User.is_active == True, User.phone_normalized == target)  # noqa: E712
        .first()
    )
