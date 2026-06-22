from uuid import UUID, uuid4

import pytest

from app.core.database import SessionLocal
from app.models.user import User
from app.services.identity_service import resolve_sender

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def test_resolves_known_professional_by_phone(db):
    email = f"id-{uuid4().hex[:8]}@example.com"
    user = User(id=uuid4(), email=email, name="Profissional", phone="+55 (51) 99999-8888")
    db.add(user)
    db.commit()
    try:
        found = resolve_sender(db, "5551999998888@s.whatsapp.net")
        assert found is not None and found.id == user.id
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()


def test_unknown_number_returns_none(db):
    assert resolve_sender(db, "5551000000000") is None


def test_blank_phone_returns_none(db):
    assert resolve_sender(db, "") is None
