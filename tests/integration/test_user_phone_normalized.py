from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.user import User
from app.services.identity_service import resolve_sender


def _new_user(phone):
    return User(id=uuid4(), email=f"u-{uuid4().hex[:8]}@example.com", name="Pro", phone=phone)


def test_validates_sets_phone_normalized_on_assignment():
    u = _new_user("+55 (51) 99999-8888")
    assert u.phone_normalized == "5551999998888"


def test_blank_phone_yields_null_normalized():
    u = _new_user(None)
    assert u.phone_normalized is None


def test_two_users_same_normalized_phone_violate_unique():
    db = SessionLocal()
    a = _new_user("+5551999998888")
    b = _new_user("51 99999-8888")  # normalizes to the same 5551999998888
    db.add(a)
    db.commit()
    try:
        db.add(b)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.query(User).filter(User.id.in_([a.id, b.id])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_resolve_sender_matches_on_normalized_column():
    db = SessionLocal()
    u = _new_user("+55 (51) 98888-7777")
    db.add(u)
    db.commit()
    try:
        found = resolve_sender(db, "5551988887777@s.whatsapp.net")
        assert found is not None and found.id == u.id
    finally:
        db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
        db.commit()
        db.close()
