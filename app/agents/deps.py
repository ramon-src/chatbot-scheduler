"""Typed dependencies injected into the SimplificaAgent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.client_service import ClientService

if TYPE_CHECKING:
    from app.channels.outbound import OutboundAdapter
    from app.services.event_service import EventService
    from app.services.google_calendar_service import GoogleCalendarService
    from app.services.lead_service import LeadService


@dataclass
class AgentDeps:
    db: Session
    user_id: UUID
    user_name: str | None
    current_datetime: datetime
    timezone: str
    history_summary: str | None
    client_service: ClientService
    calendar_service: GoogleCalendarService | None = field(default=None)
    event_service: EventService | None = field(default=None)
    outbound: "OutboundAdapter | None" = field(default=None)
    default_consult_minutes: int = 60


@dataclass
class LeadAgentDeps:
    db: Session
    lead_id: "UUID"
    lead_name: str | None
    lead_phone: str
    current_datetime: datetime
    timezone: str
    history_summary: str | None
    lead_service: "LeadService"
    trial_days: int
