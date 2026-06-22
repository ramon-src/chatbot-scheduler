# tests/unit/test_lead_service.py
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import ConflictError
from app.models.lead import Lead
from app.models.user import User
from app.services.lead_service import LeadService

TZ = ZoneInfo(settings.TIMEZONE)


def _cleanup(db, phone, email):
    db.query(Lead).filter(Lead.phone == phone).delete()
    db.query(User).filter(User.email == email).delete()
    db.commit()


def test_get_or_create_lead_is_idempotent():
    db = SessionLocal()
    phone = "5551900000020"
    try:
        svc = LeadService(db)
        a = svc.get_or_create_lead(phone)
        b = svc.get_or_create_lead(phone)
        assert a.id == b.id
    finally:
        _cleanup(db, phone, "x@x")
        db.close()


def test_convert_creates_user_in_trial_and_marks_lead():
    db = SessionLocal()
    phone = "5551900000021"
    email = "lead-convert-test@simplificapsi.test"
    try:
        svc = LeadService(db)
        lead = svc.get_or_create_lead(phone)
        user, created = svc.convert_to_account(lead, "Carla Nova", email, trial_days=7)
        assert created is True
        assert user.access_expires_at is not None
        assert user.access_expires_at > datetime.now(TZ)
        db.refresh(lead)
        assert lead.status == "converted"
        assert lead.user_id == user.id
    finally:
        _cleanup(db, phone, email)
        db.close()


def test_convert_is_idempotent_on_existing_phone():
    db = SessionLocal()
    phone = "5551900000022"
    email = "lead-convert-twice@simplificapsi.test"
    try:
        svc = LeadService(db)
        lead = svc.get_or_create_lead(phone)
        user1, created1 = svc.convert_to_account(lead, "Bia Dup", email, trial_days=7)
        user2, created2 = svc.convert_to_account(lead, "Bia Dup", email, trial_days=7)
        assert created1 is True and created2 is False
        assert user1.id == user2.id
    finally:
        _cleanup(db, phone, email)
        db.close()
