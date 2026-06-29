"""Deterministic, network-free calendar double for evals (never imported by production)."""

from __future__ import annotations


class FakeCalendarService:
    def __init__(self) -> None:
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"fake-{self._counter}"

    def create_event(self, *, summary, start, end, description=None, recurrence=None) -> dict:
        return {"id": self._next_id(), "html_link": None}

    def update_event(self, event_id, **changes) -> dict:
        return {"id": event_id, "html_link": None}

    def cancel_event(self, event_id) -> None:
        return None

    def cancel_occurrence(self, series_google_event_id, occurrence_start) -> None:
        return None

    def list_events(self, start, end) -> list:
        return []

    @staticmethod
    def build_weekly_rrule(weekdays, until) -> str:
        from app.services.google_calendar_service import GoogleCalendarService
        return GoogleCalendarService.build_weekly_rrule(weekdays, until)


class FakeOutboundAdapter:
    """Records outbound sends; never hits the network."""
    provider = "fake"

    def __init__(self) -> None:
        self.sent = []

    def send(self, message) -> bool:
        self.sent.append(message)
        return True
