import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.lead import Lead


def test_create_lead_defaults_to_new():
    db = SessionLocal()
    try:
        lead = Lead(phone="5551900000001")
        db.add(lead)
        db.commit()
        db.refresh(lead)
        assert lead.status == "new"
        assert lead.user_id is None
    finally:
        db.query(Lead).filter(Lead.phone == "5551900000001").delete()
        db.commit()
        db.close()


def test_lead_phone_is_unique():
    db = SessionLocal()
    try:
        db.add(Lead(phone="5551900000002"))
        db.commit()
        db.add(Lead(phone="5551900000002"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.query(Lead).filter(Lead.phone == "5551900000002").delete()
        db.commit()
        db.close()
