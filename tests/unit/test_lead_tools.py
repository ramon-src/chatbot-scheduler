from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agents.deps import LeadAgentDeps
from app.agents.tools.lead_tools import (
    create_professional_account_impl,
    update_lead_info_impl,
)
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.lead import Lead
from app.models.user import User
from app.services.lead_service import LeadService

TZ = ZoneInfo(settings.TIMEZONE)


def _deps(db, lead):
    return LeadAgentDeps(
        db=db, lead_id=lead.id, lead_name=lead.name, lead_phone=lead.phone,
        current_datetime=datetime.now(TZ), timezone=settings.TIMEZONE,
        history_summary=None, lead_service=LeadService(db), trial_days=7,
    )


def _cleanup(db, phone, email):
    db.query(Lead).filter(Lead.phone == phone).delete()
    db.query(User).filter(User.email == email).delete()
    db.commit()


async def test_update_lead_info_persists():
    db = SessionLocal()
    phone = "5551900000030"
    try:
        lead = LeadService(db).get_or_create_lead(phone)
        out = await update_lead_info_impl(_deps(db, lead), name="Rafa Lead", status="qualified")
        assert out["success"] is True
        db.refresh(lead)
        assert lead.name == "Rafa Lead" and lead.status == "qualified"
    finally:
        _cleanup(db, phone, "x@x")
        db.close()


async def test_create_account_requires_email():
    db = SessionLocal()
    phone = "5551900000031"
    try:
        lead = LeadService(db).get_or_create_lead(phone)
        out = await create_professional_account_impl(_deps(db, lead), name="Sem Email", email=None)
        assert out["success"] is False
    finally:
        _cleanup(db, phone, "x@x")
        db.close()


async def test_create_account_success_then_idempotent():
    db = SessionLocal()
    phone = "5551900000032"
    email = "lead-tool-acct@simplificapsi.test"
    try:
        lead = LeadService(db).get_or_create_lead(phone)
        out1 = await create_professional_account_impl(_deps(db, lead), name="Nova Conta", email=email)
        assert out1["success"] is True
        out2 = await create_professional_account_impl(_deps(db, lead), name="Nova Conta", email=email)
        assert out2["success"] is True  # idempotent, friendly "já tem conta"
        # message must not leak IDs/URLs
        assert "http" not in out1["message"].lower()
    finally:
        _cleanup(db, phone, email)
        db.close()
