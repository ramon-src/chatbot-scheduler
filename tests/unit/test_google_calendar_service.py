from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.services.google_calendar_service import GoogleCalendarService

TZ = ZoneInfo("America/Sao_Paulo")


def _service_with_events(events_mock):
    resource = MagicMock()
    resource.events.return_value = events_mock
    return GoogleCalendarService(resource, timezone="America/Sao_Paulo")


def test_create_event_calls_insert_and_returns_id():
    events = MagicMock()
    events.insert.return_value.execute.return_value = {
        "id": "evt123", "htmlLink": "https://calendar.google.com/x"
    }
    svc = _service_with_events(events)
    out = svc.create_event(
        summary="Sessão - Maria",
        start=datetime(2026, 6, 22, 10, 0, tzinfo=TZ),
        end=datetime(2026, 6, 22, 11, 0, tzinfo=TZ),
    )
    assert out["id"] == "evt123"
    _, kwargs = events.insert.call_args
    assert kwargs["calendarId"] == "primary"
    body = kwargs["body"]
    assert body["summary"] == "Sessão - Maria"
    assert body["start"]["timeZone"] == "America/Sao_Paulo"
    assert body["start"]["dateTime"].startswith("2026-06-22T10:00:00")


def test_create_event_includes_recurrence_when_given():
    events = MagicMock()
    events.insert.return_value.execute.return_value = {"id": "r1", "htmlLink": "u"}
    svc = _service_with_events(events)
    svc.create_event(
        summary="x",
        start=datetime(2026, 6, 22, 10, 0, tzinfo=TZ),
        end=datetime(2026, 6, 22, 11, 0, tzinfo=TZ),
        recurrence=["RRULE:FREQ=WEEKLY;BYDAY=MO"],
    )
    body = events.insert.call_args.kwargs["body"]
    assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO"]


def test_list_events_normalizes_items():
    events = MagicMock()
    events.list.return_value.execute.return_value = {
        "items": [
            {"id": "a", "summary": "Sessão - João",
             "start": {"dateTime": "2026-06-22T10:00:00-03:00"},
             "end": {"dateTime": "2026-06-22T11:00:00-03:00"}},
        ]
    }
    svc = _service_with_events(events)
    out = svc.list_events(datetime(2026, 6, 22, tzinfo=TZ), datetime(2026, 6, 23, tzinfo=TZ))
    assert out[0]["id"] == "a"
    assert out[0]["summary"] == "Sessão - João"
    assert out[0]["start"].hour == 10
    assert events.list.call_args.kwargs["singleEvents"] is True
    assert events.list.call_args.kwargs["orderBy"] == "startTime"


def test_cancel_event_deletes():
    events = MagicMock()
    svc = _service_with_events(events)
    svc.cancel_event("evt999")
    assert events.delete.call_args.kwargs["eventId"] == "evt999"
    events.delete.return_value.execute.assert_called_once()


def test_build_weekly_rrule_with_until():
    rule = GoogleCalendarService.build_weekly_rrule(["TU"], datetime(2026, 12, 31, 0, 0, tzinfo=TZ))
    assert rule.startswith("RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=")


def test_build_weekly_rrule_without_until():
    rule = GoogleCalendarService.build_weekly_rrule(None, None)
    assert rule == "RRULE:FREQ=WEEKLY"
