"""Thin wrapper over the Google Calendar v3 API resource (injected)."""

from datetime import datetime, timezone


class GoogleCalendarService:
    def __init__(self, resource, timezone: str, calendar_id: str = "primary"):
        self._events = resource.events()
        self._tz = timezone
        self._calendar_id = calendar_id

    def _dt(self, value: datetime) -> dict:
        return {"dateTime": value.isoformat(), "timeZone": self._tz}

    @staticmethod
    def _parse(node: dict) -> datetime:
        raw = node.get("dateTime") or node.get("date")
        return datetime.fromisoformat(raw)

    def create_event(self, summary, start, end, description=None, recurrence=None) -> dict:
        body = {"summary": summary, "start": self._dt(start), "end": self._dt(end)}
        if description:
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

    @staticmethod
    def build_weekly_rrule(weekdays, until) -> str:
        rule = "RRULE:FREQ=WEEKLY"
        if weekdays:
            rule += f";BYDAY={','.join(weekdays)}"
        if until is not None:
            until_utc = until.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            rule += f";UNTIL={until_utc}"
        return rule
