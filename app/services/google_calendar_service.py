"""Thin wrapper over the Google Calendar v3 API resource (injected)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


class GoogleCalendarService:
    def __init__(self, resource, timezone: str, calendar_id: str = "primary"):
        self._resource = resource
        self._events = resource.events()
        self._tz = timezone
        self._calendar_id = calendar_id

    def _dt(self, value: datetime) -> dict:
        return {"dateTime": value.isoformat(), "timeZone": self._tz}

    def _parse(self, node: dict) -> datetime:
        """Parse a GCal start/end node to a timezone-aware datetime.

        `dateTime` nodes carry an offset; all-day `date` nodes are naive, so we
        anchor them to the service timezone at midnight to keep the aware contract.
        """
        if node.get("dateTime"):
            return datetime.fromisoformat(node["dateTime"])
        parsed = datetime.fromisoformat(node["date"])
        return parsed.replace(tzinfo=ZoneInfo(self._tz))

    def create_event(self, summary, start, end, description=None, recurrence=None) -> dict:
        body = {"summary": summary, "start": self._dt(start), "end": self._dt(end)}
        if description is not None:
            body["description"] = description
        if recurrence:
            body["recurrence"] = recurrence
        created = self._events.insert(calendarId=self._calendar_id, body=body).execute()
        return {"id": created["id"], "html_link": created.get("htmlLink")}

    def list_events(self, start, end) -> list[dict]:
        resp = self._events.list(
            calendarId=self._calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        items = []
        for item in resp.get("items", []):
            items.append({
                "id": item["id"],
                "summary": item.get("summary", ""),
                "start": self._parse(item["start"]),
                "end": self._parse(item["end"]),
            })
        return items

    def update_event(self, event_id, **changes) -> dict:
        body = {}
        if "summary" in changes and changes["summary"] is not None:
            body["summary"] = changes["summary"]
        if "description" in changes and changes["description"] is not None:
            body["description"] = changes["description"]
        if changes.get("start") is not None:
            body["start"] = self._dt(changes["start"])
        if changes.get("end") is not None:
            body["end"] = self._dt(changes["end"])
        updated = self._events.patch(
            calendarId=self._calendar_id, eventId=event_id, body=body
        ).execute()
        return {"id": updated["id"], "html_link": updated.get("htmlLink")}

    def cancel_event(self, event_id) -> None:
        self._events.delete(calendarId=self._calendar_id, eventId=event_id).execute()

    def create_calendar(self, summary: str) -> dict:
        body = {"summary": summary, "timeZone": self._tz}
        created = self._resource.calendars().insert(body=body).execute()
        return {"id": created["id"]}

    def share_calendar(self, calendar_id: str, email: str, role: str = "writer") -> None:
        self._resource.acl().insert(
            calendarId=calendar_id,
            body={"role": role, "scope": {"type": "user", "value": email}},
        ).execute()

    def delete_calendar(self, calendar_id: str) -> None:
        self._resource.calendars().delete(calendarId=calendar_id).execute()

    @staticmethod
    def build_weekly_rrule(weekdays, until) -> str:
        rule = "RRULE:FREQ=WEEKLY"
        if weekdays:
            rule += f";BYDAY={','.join(weekdays)}"
        if until is not None:
            until_utc = until.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
            rule += f";UNTIL={until_utc}"
        return rule
