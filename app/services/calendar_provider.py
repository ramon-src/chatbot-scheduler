"""Resolve, per user, which Google auth mode + calendar to use.

OAuth (the professional's own account) takes priority; otherwise the service
account is the zero-friction default (a calendar created under the SA, shared
best-effort with the professional). Returns None when neither is available.
"""

from dataclasses import dataclass

from app.models.calendar import Calendar
from app.services.event_service import EventService
from app.services.google_auth import (
    build_service_account_credentials,
    has_credentials,
    load_credentials,
)
from app.services.google_calendar_service import GoogleCalendarService


@dataclass
class CalendarAccess:
    service: GoogleCalendarService
    calendar: Calendar


def _default_build_resource(credentials):
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def build_calendar_access(db, user, settings, *, build_resource=None, event_service=None):
    build_resource = build_resource or _default_build_resource
    es = event_service or EventService(db)
    tz = settings.TIMEZONE

    # 1. OAuth takes priority — the professional's own calendar.
    if has_credentials(db, user.id):
        try:
            creds = load_credentials(db, user.id)
            resource = build_resource(creds)
            cal = es.ensure_calendar(user.id, "primary")
            return CalendarAccess(GoogleCalendarService(resource, tz, calendar_id="primary"), cal)
        except Exception:  # noqa: BLE001 - broken OAuth → not connected (do NOT fall back to SA)
            return None

    # 2. Service account — zero-friction default.
    sa_creds = build_service_account_credentials(settings)
    if sa_creds is None:
        return None
    try:
        resource = build_resource(sa_creds)
        svc = GoogleCalendarService(resource, tz)

        existing = es.get_existing_primary(user.id)
        if existing is not None and existing.google_calendar_id and existing.google_calendar_id != "primary":
            cal = existing
        else:
            name = f"SimplificaPsi — {user.name}"
            created = svc.create_calendar(name)
            email = getattr(user, "email", None)
            if email:
                try:
                    svc.share_calendar(created["id"], email)
                except Exception:  # noqa: BLE001 - best-effort; non-Google email etc.
                    pass
            cal = es.ensure_calendar(user.id, created["id"], name=name)

        bound = GoogleCalendarService(resource, tz, calendar_id=cal.google_calendar_id)
        return CalendarAccess(bound, cal)
    except Exception:  # noqa: BLE001 - never let calendar setup 500 the chat
        return None
