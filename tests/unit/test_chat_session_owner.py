import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.chat_session import ChatSession
from app.models.lead import Lead


def test_lead_owned_session_is_allowed():
    db = SessionLocal()
    try:
        lead = Lead(phone="5551900000010")
        db.add(lead)
        db.commit()
        db.refresh(lead)
        s = ChatSession(lead_id=lead.id, session_id="sess-lead-1", phone_number="5551900000010")
        db.add(s)
        db.commit()
        db.refresh(s)
        assert s.user_id is None and s.lead_id == lead.id
    finally:
        db.rollback()
        db.query(ChatSession).filter(ChatSession.session_id == "sess-lead-1").delete()
        db.query(Lead).filter(Lead.phone == "5551900000010").delete()
        db.commit()
        db.close()


def test_session_rejects_two_owners():
    db = SessionLocal()
    try:
        lead = Lead(phone="5551900000011")
        db.add(lead)
        db.commit()
        db.refresh(lead)
        # both user_id and lead_id set -> CHECK violation
        from uuid import uuid4
        s = ChatSession(user_id=uuid4(), lead_id=lead.id, session_id="sess-bad", phone_number="x")
        db.add(s)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.query(Lead).filter(Lead.phone == "5551900000011").delete()
        db.commit()
        db.close()
