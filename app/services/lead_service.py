"""Lead persistence + qualification funnel operations."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.channels.phone import normalize_phone
from app.core.config import settings
from app.core.exceptions import ConflictError
from app.models.lead import Lead
from app.models.user import User


class LeadService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_lead(self, phone: str) -> Lead:
        lead = self.db.query(Lead).filter(Lead.phone == phone).first()
        if lead is not None:
            return lead
        lead = Lead(phone=phone, status="new")
        self.db.add(lead)
        try:
            self.db.commit()
        except IntegrityError:  # concurrent insert on the unique phone
            self.db.rollback()
            return self.db.query(Lead).filter(Lead.phone == phone).first()
        self.db.refresh(lead)
        return lead

    def get_lead(self, lead_id: UUID) -> Lead | None:
        return self.db.get(Lead, lead_id)

    def update_lead(
        self, lead: Lead, *, name=None, email=None, notes=None, status=None
    ) -> Lead:
        if name is not None:
            lead.name = name
        if email is not None:
            lead.email = email
        if notes is not None:
            lead.notes = notes
        if status is not None:
            lead.status = status
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def convert_to_account(
        self, lead: Lead, name: str, email: str, trial_days: int
    ) -> tuple[User, bool]:
        """Create the professional's trial account from a lead. Idempotent on phone."""
        normalized = normalize_phone(lead.phone)
        existing = (
            self.db.query(User).filter(User.phone_normalized == normalized).first()
            if normalized
            else None
        )
        if existing is not None:
            self._mark_converted(lead, existing.id)
            return existing, False

        expires = datetime.now(ZoneInfo(settings.TIMEZONE)) + timedelta(days=trial_days)
        user = User(name=name, email=email, phone=lead.phone, access_expires_at=expires)
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = (
                self.db.query(User).filter(User.phone_normalized == normalized).first()
                if normalized
                else None
            )
            if existing is not None:
                self._mark_converted(lead, existing.id)
                return existing, False
            raise ConflictError("Já existe uma conta com esse e-mail.")
        self.db.refresh(user)
        self._mark_converted(lead, user.id)
        return user, True

    def _mark_converted(self, lead: Lead, user_id: UUID) -> None:
        lead.status = "converted"
        lead.user_id = user_id
        self.db.commit()
