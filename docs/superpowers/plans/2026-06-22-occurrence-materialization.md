# Occurrence Materialization + Billable (Slice 3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materialize each recurring session as its own mirror row (listable, cancellable, priced) and record a per-session `billable` decision, so billing (slice 3b) can track payment per occurrence and cancelled/no-show sessions can be charged or waived.

**Architecture:** A recurring series stays as one "template" row (`is_recurring=true`, `parent_event_id` NULL). On read, `EventService.ensure_occurrences(range)` lazily and idempotently expands the template's RRULE into per-occurrence rows (`parent_event_id` set, `occurrence_date` set) within the queried range. `list_events`/`cancel_event` operate on occurrences + single events, excluding templates and cancelled rows. `Event.billable` captures the professional's charge decision; `cancel_event` sets it (default: cancellation not charged) and a new `set_session_charge` tool adjusts it later.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 (Column-style models), Alembic (schema `simplificapsi`), Pydantic AI, python-dateutil (RRULE expansion), pytest (asyncio_mode=auto), ruff, uv.

## Global Constraints

- Code, identifiers, enums in English; user-facing copy PT-BR.
- DB schema always `simplificapsi`.
- Migrations chain linearly: 0010 → 0009_users_phone_normalized; single head after.
- Tool contract `{"success": bool, "data": Any, "message": str}`; `message` never contains IDs/JSON/URLs.
- Google Calendar is the agenda source of truth, but the Postgres mirror is authoritative for the agent's reads/cancels (v1 stance). Google single-instance cancel is best-effort.
- Timezone fixed `America/Sao_Paulo`; all datetimes tz-aware.
- No billing logic in this slice (that is 3b): no `payment_model`, no billing service/tools.
- Materialization must be idempotent and bounded by the queried range (never fully expand an open-ended series).

---

## Row taxonomy (after this slice)

- **Single session:** `is_recurring=false`, `parent_event_id=NULL`. Billable session.
- **Series template:** `is_recurring=true`, `parent_event_id=NULL`, `recurrence_rule` set. NOT a session — excluded from listings. Expansion source.
- **Occurrence:** `parent_event_id` set, `occurrence_date` set, `is_recurring=false`. Billable session of a series.

---

### Task 1: Event model — `parent_event_id`, `occurrence_date`, `billable` + migration 0010

**Files:**
- Modify: `app/models/event.py`
- Create: `migrations/versions/0010_event_occurrences.py`
- Test: `tests/unit/test_event_occurrence_model.py`

**Interfaces:**
- Produces: `Event.parent_event_id` (UUID null, self-FK), `Event.occurrence_date` (Date null), `Event.billable` (Boolean, default True); unique constraint `uq_event_occurrence` on `(parent_event_id, occurrence_date)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_event_occurrence_model.py
from app.models.event import Event


def test_occurrence_columns_exist():
    cols = Event.__table__.columns
    assert "parent_event_id" in cols
    assert "occurrence_date" in cols
    assert "billable" in cols


def test_unique_occurrence_constraint():
    uniques = [
        tuple(sorted(c.name for c in con.columns))
        for con in Event.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("occurrence_date", "parent_event_id") in uniques
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_event_occurrence_model.py -v`
Expected: FAIL (columns/constraint absent)

- [ ] **Step 3: Implement**

In `app/models/event.py`: add `Date` and `UniqueConstraint` to the `sqlalchemy` import:

```python
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
```

Change `__table_args__` to a tuple carrying the unique constraint:

```python
    __table_args__ = (
        UniqueConstraint("parent_event_id", "occurrence_date", name="uq_event_occurrence"),
        {"schema": "simplificapsi"},
    )
```

Add the columns in the FOREIGN KEYS / RECURRENCE area (after `recurrence_rule`):

```python
    parent_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simplificapsi.events.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    occurrence_date = Column(Date, nullable=True, index=True)
```

Add `billable` in the STATUS area (after `payment_status`):

```python
    billable = Column(Boolean, default=True, server_default="true", nullable=False, index=True)
```

Create the migration:

```python
# migrations/versions/0010_event_occurrences.py
"""add occurrence + billable columns to events

Recurring sessions are materialized as per-occurrence rows (parent_event_id +
occurrence_date); billable records whether a session counts for billing.

Revision ID: 0010_event_occurrences
Revises: 0009_users_phone_normalized
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_event_occurrences"
down_revision = "0009_users_phone_normalized"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("parent_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="simplificapsi",
    )
    op.add_column(
        "events",
        sa.Column("occurrence_date", sa.Date(), nullable=True),
        schema="simplificapsi",
    )
    op.add_column(
        "events",
        sa.Column("billable", sa.Boolean(), server_default="true", nullable=False),
        schema="simplificapsi",
    )
    op.create_foreign_key(
        "fk_events_parent_event_id", "events", "events",
        ["parent_event_id"], ["id"],
        source_schema="simplificapsi", referent_schema="simplificapsi",
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_simplificapsi_events_parent_event_id", "events", ["parent_event_id"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_events_occurrence_date", "events", ["occurrence_date"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_events_billable", "events", ["billable"],
        schema="simplificapsi",
    )
    op.create_unique_constraint(
        "uq_event_occurrence", "events", ["parent_event_id", "occurrence_date"],
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_constraint("uq_event_occurrence", "events", schema="simplificapsi", type_="unique")
    op.drop_index("ix_simplificapsi_events_billable", table_name="events", schema="simplificapsi")
    op.drop_index("ix_simplificapsi_events_occurrence_date", table_name="events", schema="simplificapsi")
    op.drop_index("ix_simplificapsi_events_parent_event_id", table_name="events", schema="simplificapsi")
    op.drop_constraint("fk_events_parent_event_id", "events", schema="simplificapsi", type_="foreignkey")
    op.drop_column("events", "billable", schema="simplificapsi")
    op.drop_column("events", "occurrence_date", schema="simplificapsi")
    op.drop_column("events", "parent_event_id", schema="simplificapsi")
```

- [ ] **Step 4: Run test + migration**

Run: `uv run pytest tests/unit/test_event_occurrence_model.py -v`
Expected: PASS

Run: `uv run alembic upgrade head`
Expected: `0009_users_phone_normalized -> 0010_event_occurrences` applies cleanly.

- [ ] **Step 5: Commit**

```bash
git add app/models/event.py migrations/versions/0010_event_occurrences.py tests/unit/test_event_occurrence_model.py
git commit -m "feat(agenda): event occurrence + billable columns (migration 0010)"
```

---

### Task 2: `EventService.ensure_occurrences` — lazy idempotent materialization

**Files:**
- Modify: `app/services/event_service.py`
- Modify: `pyproject.toml` (declare `python-dateutil` if absent)
- Test: `tests/integration/test_ensure_occurrences.py`

**Interfaces:**
- Consumes: `Event` (Task 1), `recurrence_rule` strings produced by `GoogleCalendarService.build_weekly_rrule` (form: `"RRULE:FREQ=WEEKLY;BYDAY=TU,TH[;UNTIL=YYYYMMDDTHHMMSSZ]"`).
- Produces: `EventService.ensure_occurrences(self, user_id: UUID, range_start: datetime, range_end: datetime) -> int` — materializes missing occurrence rows for the user's series templates overlapping the range; returns the count created. Idempotent.

Helper for templates: a template is `is_recurring == True`, `parent_event_id IS NULL`, `status != cancelled`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_ensure_occurrences.py
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.database import SessionLocal
from app.models.client import Client
from app.models.event import Event, EventStatus
from app.services.event_service import EventService

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def seeded():
    """A weekly Tuesday 09:00 series template + its client, cleaned up after."""
    db = SessionLocal()
    client = Client(
        id=uuid4(), user_id=DEV_USER_ID, name="Recorrente Teste",
        phone=f"+5551{uuid4().int % 1000000000:09d}", invoice_day=10,
        consult_price=Decimal("180"), is_active=True,
    )
    db.add(client)
    db.commit()
    svc = EventService(db)
    cal = svc.get_primary_calendar(DEV_USER_ID)
    # First Tuesday 09:00 of a fixed reference week
    start = datetime(2026, 7, 7, 9, 0, tzinfo=TZ)  # a Tuesday
    template = Event(
        id=uuid4(), user_id=DEV_USER_ID, client_id=client.id, calendar_id=cal.id,
        title="Sessão - Recorrente Teste", start_time=start, end_time=start + timedelta(hours=1),
        is_recurring=True, recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=TU",
        google_event_id=f"series-{uuid4().hex[:8]}", status=EventStatus.SCHEDULED.value,
        price=None,
    )
    db.add(template)
    db.commit()
    yield db, client, template, start
    db.query(Event).filter(
        (Event.id == template.id) | (Event.parent_event_id == template.id)
    ).delete(synchronize_session=False)
    db.query(Client).filter(Client.id == client.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_materializes_one_row_per_week(seeded):
    db, client, template, start = seeded
    svc = EventService(db)
    range_start = start
    range_end = start + timedelta(days=21)  # 3 weeks
    created = svc.ensure_occurrences(DEV_USER_ID, range_start, range_end)
    assert created == 3
    occ = db.query(Event).filter(Event.parent_event_id == template.id).order_by(Event.start_time).all()
    assert [e.occurrence_date.isoformat() for e in occ] == ["2026-07-07", "2026-07-14", "2026-07-21"]
    # price falls back to the client's consult_price; sessions are billable
    assert all(e.price == Decimal("180") for e in occ)
    assert all(e.billable is True for e in occ)
    assert all(e.parent_event_id == template.id and not e.is_recurring for e in occ)


def test_is_idempotent(seeded):
    db, client, template, start = seeded
    svc = EventService(db)
    rs, re_ = start, start + timedelta(days=21)
    svc.ensure_occurrences(DEV_USER_ID, rs, re_)
    created_again = svc.ensure_occurrences(DEV_USER_ID, rs, re_)
    assert created_again == 0
    assert db.query(Event).filter(Event.parent_event_id == template.id).count() == 3


def test_respects_until(seeded):
    db, client, template, start = seeded
    template.recurrence_rule = "RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20260715T120000Z"
    db.commit()
    svc = EventService(db)
    created = svc.ensure_occurrences(DEV_USER_ID, start, start + timedelta(days=28))
    # only 2026-07-07 and 2026-07-14 fall on/before the UNTIL
    assert created == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_ensure_occurrences.py -v`
Expected: FAIL (`ensure_occurrences` does not exist)

- [ ] **Step 3: Implement**

Ensure `python-dateutil` is a declared dependency in `pyproject.toml` (it is already installed transitively; add it to the `[project] dependencies` list if not present, e.g. `"python-dateutil>=2.9"`).

In `app/services/event_service.py`, add imports:

```python
from datetime import date, datetime, timedelta
from dateutil.rrule import rrulestr

from app.models.client import Client
from app.models.event import Event, EventStatus, PaymentStatus
```

(Keep existing imports; `PaymentStatus` and `Client` are new here.)

Add the method to `EventService`:

```python
    def _series_templates(self, user_id: UUID) -> list[Event]:
        return self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.is_recurring == True,  # noqa: E712
                Event.parent_event_id.is_(None),
                Event.status != EventStatus.CANCELLED.value,
            )
        ).all()

    def ensure_occurrences(self, user_id: UUID, range_start: datetime, range_end: datetime) -> int:
        """Idempotently materialize per-occurrence rows for the user's recurring
        series within [range_start, range_end]. Returns the number created."""
        created = 0
        for template in self._series_templates(user_id):
            rule_text = (template.recurrence_rule or "").removeprefix("RRULE:")
            if not rule_text:
                continue
            rule = rrulestr(rule_text, dtstart=template.start_time)
            duration = template.end_time - template.start_time
            existing = {
                row.occurrence_date
                for row in self.db.query(Event.occurrence_date).filter(
                    Event.parent_event_id == template.id
                )
            }
            client = self.db.get(Client, template.client_id) if template.client_id else None
            fallback_price = client.consult_price if client is not None else None
            for occ_start in rule.between(range_start, range_end, inc=True):
                occ_date = occ_start.date()
                if occ_date in existing:
                    continue
                self.db.add(Event(
                    user_id=user_id, client_id=template.client_id,
                    calendar_id=template.calendar_id, title=template.title,
                    start_time=occ_start, end_time=occ_start + duration,
                    parent_event_id=template.id, occurrence_date=occ_date,
                    is_recurring=False, google_event_id=None,
                    status=EventStatus.SCHEDULED.value,
                    payment_status=PaymentStatus.PENDING.value,
                    price=template.price if template.price is not None else fallback_price,
                    billable=True,
                ))
                existing.add(occ_date)
                created += 1
        if created:
            self.db.commit()
        return created
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_ensure_occurrences.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/event_service.py pyproject.toml tests/integration/test_ensure_occurrences.py
git commit -m "feat(agenda): lazy idempotent occurrence materialization"
```

---

### Task 3: `list_events` shows occurrences; `create_event` stamps price

**Files:**
- Modify: `app/services/event_service.py` (exclude templates in range listing)
- Modify: `app/agents/tools/calendar_tools.py` (list calls ensure_occurrences; single create stamps price)
- Test: `tests/integration/test_list_occurrences.py`

**Interfaces:**
- Consumes: `ensure_occurrences` (Task 2).
- Produces: `list_events_in_range` excludes series templates (`is_recurring=true AND parent_event_id IS NULL`); `list_events_impl` materializes the range first; `create_event_impl` records `price=client.consult_price`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_list_occurrences.py
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.database import SessionLocal
from app.models.client import Client
from app.models.event import Event, EventStatus
from app.services.event_service import EventService

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def weekly_series():
    db = SessionLocal()
    client = Client(
        id=uuid4(), user_id=DEV_USER_ID, name="Lista Recorrente",
        phone=f"+5551{uuid4().int % 1000000000:09d}", invoice_day=5,
        consult_price=Decimal("150"), is_active=True,
    )
    db.add(client)
    db.commit()
    svc = EventService(db)
    cal = svc.get_primary_calendar(DEV_USER_ID)
    start = datetime(2026, 7, 7, 9, 0, tzinfo=TZ)
    template = Event(
        id=uuid4(), user_id=DEV_USER_ID, client_id=client.id, calendar_id=cal.id,
        title="Sessão - Lista Recorrente", start_time=start, end_time=start + timedelta(hours=1),
        is_recurring=True, recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=TU",
        google_event_id=f"series-{uuid4().hex[:8]}", status=EventStatus.SCHEDULED.value,
    )
    db.add(template)
    db.commit()
    yield db, client, template, start
    db.query(Event).filter(
        (Event.id == template.id) | (Event.parent_event_id == template.id)
    ).delete(synchronize_session=False)
    db.query(Client).filter(Client.id == client.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_series_appears_in_later_weeks_and_template_hidden(weekly_series):
    db, client, template, start = weekly_series
    svc = EventService(db)
    # week 2 window
    w2_start = start + timedelta(days=7)
    svc.ensure_occurrences(DEV_USER_ID, w2_start, w2_start + timedelta(days=1))
    rows = svc.list_events_in_range(DEV_USER_ID, w2_start, w2_start + timedelta(days=1))
    # the occurrence shows; the template (is_recurring + no parent) does not
    assert len(rows) == 1
    assert rows[0].parent_event_id == template.id
    assert all(not (r.is_recurring and r.parent_event_id is None) for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_list_occurrences.py -v`
Expected: FAIL (template currently included; or occurrence absent)

- [ ] **Step 3: Implement**

In `app/services/event_service.py`, exclude templates in `list_events_in_range`:

```python
    def list_events_in_range(self, user_id: UUID, start: datetime, end: datetime) -> list[Event]:
        return self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.start_time >= start,
                Event.start_time < end,
                Event.status != EventStatus.CANCELLED.value,
                # exclude series templates (the expansion source is not a session)
                ~and_(Event.is_recurring == True, Event.parent_event_id.is_(None)),  # noqa: E712
            )
        ).order_by(Event.start_time).all()
```

In `app/agents/tools/calendar_tools.py`, have `list_events_impl` materialize first. After computing `start, end` and before listing:

```python
    deps.event_service.ensure_occurrences(deps.user_id, start, end)
    events = deps.event_service.list_events_in_range(deps.user_id, start, end)
```

In `create_event_impl`, stamp the price from the resolved client when recording:

```python
        deps.event_service.record_event(
            user_id=deps.user_id, client_id=client.id, title=summary,
            start=start_time, end=end, google_event_id=created["id"],
            price=client.consult_price,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_list_occurrences.py tests/unit/test_calendar_tools.py -v`
Expected: PASS (new occurrence listing + existing calendar tool tests stay green)

- [ ] **Step 5: Commit**

```bash
git add app/services/event_service.py app/agents/tools/calendar_tools.py tests/integration/test_list_occurrences.py
git commit -m "feat(agenda): list materialized occurrences; stamp price on single events"
```

---

### Task 4: `cancel_event` — charge decision + occurrence cancel + best-effort Google instance

**Files:**
- Modify: `app/services/google_calendar_service.py` (add `cancel_occurrence`)
- Modify: `app/services/event_service.py` (`cancel_event` sets billable)
- Modify: `app/agents/tools/calendar_tools.py` (`cancel_event_impl` + tool signature)
- Test: `tests/unit/test_cancel_charge.py`

**Interfaces:**
- Consumes: `ensure_occurrences`, `list_events_in_range` (templates excluded).
- Produces:
  - `GoogleCalendarService.cancel_occurrence(series_google_event_id, occurrence_start)` — best-effort cancel of one instance.
  - `EventService.cancel_event(event, billable=None)` — also sets `billable` when provided.
  - `cancel_event_impl(..., charge: bool | None = None)` and the `cancel_event` tool gains `charge`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cancel_charge.py
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.agents.tools.calendar_tools import cancel_event_impl
from app.models.event import EventStatus

TZ = ZoneInfo("America/Sao_Paulo")


def _deps(events, client):
    calendar_service = MagicMock()
    event_service = MagicMock()
    event_service.list_events_in_range.return_value = events
    event_service.ensure_occurrences.return_value = 0

    def _cancel(ev, billable=None):
        ev.status = EventStatus.CANCELLED.value
        if billable is not None:
            ev.billable = billable
        return ev
    event_service.cancel_event.side_effect = _cancel

    deps = SimpleNamespace(
        calendar_service=calendar_service, event_service=event_service,
        user_id=uuid4(), timezone="America/Sao_Paulo",
        current_datetime=datetime(2026, 7, 7, 8, 0, tzinfo=TZ),
        client_service=MagicMock(),
    )
    deps.client_service.find_by_name.return_value = client
    deps.client_service.find_by_phone.return_value = client
    return deps


def _event(client_id, start, *, google_id="g1", parent=None):
    return SimpleNamespace(
        id=uuid4(), client_id=client_id, start_time=start,
        google_event_id=google_id, parent_event_id=parent, billable=True,
        status=EventStatus.SCHEDULED.value,
    )


async def test_cancel_default_is_not_billable():
    client = SimpleNamespace(id=uuid4(), name="Joao Silva")
    ev = _event(client.id, datetime(2026, 7, 7, 9, 0, tzinfo=TZ))
    deps = _deps([ev], client)
    res = await cancel_event_impl(deps, client_name="Joao", period="today")
    assert res["success"] is True
    assert ev.billable is False  # cancellation defaults to not charged


async def test_cancel_with_charge_keeps_billable():
    client = SimpleNamespace(id=uuid4(), name="Joao Silva")
    ev = _event(client.id, datetime(2026, 7, 7, 9, 0, tzinfo=TZ))
    deps = _deps([ev], client)
    res = await cancel_event_impl(deps, client_name="Joao", period="today", charge=True)
    assert res["success"] is True
    assert ev.billable is True


async def test_cancel_occurrence_uses_best_effort_instance_cancel():
    client = SimpleNamespace(id=uuid4(), name="Joao Silva")
    parent = uuid4()
    ev = _event(client.id, datetime(2026, 7, 7, 9, 0, tzinfo=TZ), google_id=None, parent=parent)
    deps = _deps([ev], client)
    deps.event_service.get_event.return_value = SimpleNamespace(google_event_id="series-1")
    res = await cancel_event_impl(deps, client_name="Joao", period="today")
    assert res["success"] is True
    # occurrence (google_event_id is None) → cancel_occurrence path, not cancel_event
    deps.calendar_service.cancel_occurrence.assert_called_once()
    deps.calendar_service.cancel_event.assert_not_called()
```

(Note: the test references `deps.client_service.find_by_name`/`find_by_phone` and `deps.event_service.get_event`. The implementer must match the actual client-resolution helper used by `_resolve_client` in calendar_tools — read it first and align the mock to the real method names; the assertion intent, not the exact mock attribute, is what must hold. Use `event_service.get_event(parent_event_id)` to fetch the parent's google id, adding that thin getter if absent.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cancel_charge.py -v`
Expected: FAIL (`charge` param/`billable` setting/`cancel_occurrence` absent)

- [ ] **Step 3: Implement**

In `app/services/google_calendar_service.py`, add a best-effort single-instance cancel:

```python
    def cancel_occurrence(self, series_google_event_id: str, occurrence_start) -> None:
        """Best-effort cancel of one instance of a recurring Google event.

        Locates the instance starting at `occurrence_start` and marks it
        cancelled. A no-op if the instance cannot be found.
        """
        resp = self._events.instances(
            calendarId=self._calendar_id, eventId=series_google_event_id
        ).execute()
        target = occurrence_start.isoformat()
        for inst in resp.get("items", []):
            inst_start = inst.get("start", {}).get("dateTime")
            if inst_start and inst_start[:19] == target[:19]:
                self._events.patch(
                    calendarId=self._calendar_id, eventId=inst["id"],
                    body={"status": "cancelled"},
                ).execute()
                return
```

In `app/services/event_service.py`, let `cancel_event` set `billable`, and add a `get_event` getter:

```python
    def get_event(self, event_id) -> Event | None:
        return self.db.get(Event, event_id)

    def cancel_event(self, event: Event, billable: bool | None = None) -> Event:
        event.status = EventStatus.CANCELLED.value
        if billable is not None:
            event.billable = billable
        self.db.commit()
        self.db.refresh(event)
        return event
```

In `app/agents/tools/calendar_tools.py`, update `cancel_event_impl` to ensure occurrences first, take `charge`, set billable, and route the Google cancel. Replace the body after resolving the client and date range:

```python
    deps.event_service.ensure_occurrences(deps.user_id, start, end)
    events = [
        e for e in deps.event_service.list_events_in_range(deps.user_id, start, end)
        if e.client_id == client.id
    ]
    if not events:
        first = client.name.split()[0]
        return {"success": False, "data": None,
                "message": f"Não encontrei compromisso de {first} nesse período."}
    if len(events) > 1:
        return {"success": False, "data": {"count": len(events)},
                "message": "Encontrei mais de um compromisso nesse período. Pode me dizer o dia exato?"}

    event = events[0]
    billable = charge if charge is not None else False
    # Google is the source of truth: cancel there first (best-effort).
    try:
        if event.parent_event_id is not None:
            parent = deps.event_service.get_event(event.parent_event_id)
            if parent is not None and parent.google_event_id:
                deps.calendar_service.cancel_occurrence(parent.google_event_id, event.start_time)
        elif event.google_event_id:
            deps.calendar_service.cancel_event(event.google_event_id)
    except Exception:
        pass  # mirror is authoritative; degrade silently
    try:
        deps.event_service.cancel_event(event, billable=billable)
    except Exception:
        pass
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name},
            "message": f"Cancelei o compromisso de {first}."}
```

Update the `cancel_event_impl` signature to add `charge: bool | None = None`, and the `cancel_event` tool wrapper to accept and pass `charge` (add to the tool's parameters and docstring: "charge: se True, mantém a sessão cobrável mesmo cancelada").

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cancel_charge.py tests/live/test_agent_live.py -k cancel --co -q`
Run: `uv run pytest tests/unit/test_cancel_charge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/google_calendar_service.py app/services/event_service.py app/agents/tools/calendar_tools.py tests/unit/test_cancel_charge.py
git commit -m "feat(agenda): cancel records charge decision; best-effort Google instance cancel"
```

---

### Task 5: `set_session_charge` tool

**Files:**
- Modify: `app/services/event_service.py` (find a client's session on a date)
- Modify: `app/agents/tools/calendar_tools.py` (`set_session_charge_impl` + tool)
- Test: `tests/unit/test_set_session_charge.py`

**Interfaces:**
- Produces:
  - `EventService.find_client_session_on_date(user_id, client_id, day: date) -> Event | None` — the client's non-template session whose `occurrence_date == day` (occurrence) or `start_time` date == day (single).
  - `set_session_charge_impl(deps, *, client_name=None, client_phone=None, session_date: str, charge: bool) -> dict` and a `set_session_charge` tool.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_set_session_charge.py
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.agents.tools.calendar_tools import set_session_charge_impl

TZ = ZoneInfo("America/Sao_Paulo")


def _deps(found, client):
    event_service = MagicMock()
    event_service.find_client_session_on_date.return_value = found

    def _set(ev, value):
        ev.billable = value
        return ev
    event_service.set_billable.side_effect = _set

    deps = SimpleNamespace(
        calendar_service=MagicMock(), event_service=event_service,
        user_id=uuid4(), timezone="America/Sao_Paulo",
        current_datetime=datetime(2026, 7, 7, 8, 0, tzinfo=TZ),
        client_service=MagicMock(),
    )
    deps.client_service.find_by_name.return_value = client
    deps.client_service.find_by_phone.return_value = client
    return deps


async def test_sets_billable_true():
    client = SimpleNamespace(id=uuid4(), name="Maria Souza")
    ev = SimpleNamespace(id=uuid4(), billable=False)
    deps = _deps(ev, client)
    res = await set_session_charge_impl(deps, client_name="Maria", session_date="2026-07-07", charge=True)
    assert res["success"] is True
    assert ev.billable is True
    # message carries no id
    assert str(ev.id) not in res["message"]


async def test_unknown_session_is_reported():
    client = SimpleNamespace(id=uuid4(), name="Maria Souza")
    deps = _deps(None, client)
    res = await set_session_charge_impl(deps, client_name="Maria", session_date="2026-07-09", charge=False)
    assert res["success"] is False
```

(As in Task 4, align the client-resolution mock to the real helper names used by `_resolve_client`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_set_session_charge.py -v`
Expected: FAIL (`set_session_charge_impl` absent)

- [ ] **Step 3: Implement**

In `app/services/event_service.py`:

```python
    def find_client_session_on_date(self, user_id: UUID, client_id, day: date) -> Event | None:
        from sqlalchemy import cast, Date as SqlDate
        return self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.client_id == client_id,
                Event.status != EventStatus.CANCELLED.value,
                ~and_(Event.is_recurring == True, Event.parent_event_id.is_(None)),  # noqa: E712
                or_(
                    Event.occurrence_date == day,
                    cast(Event.start_time, SqlDate) == day,
                ),
            )
        ).order_by(Event.start_time).first()

    def set_billable(self, event: Event, value: bool) -> Event:
        event.billable = value
        self.db.commit()
        self.db.refresh(event)
        return event
```

Add `or_` to the sqlalchemy import in event_service.py (`from sqlalchemy import and_, or_`).

In `app/agents/tools/calendar_tools.py`, add the impl (mirror `_resolve_client` usage from the other tools) and register a `set_session_charge` tool:

```python
async def set_session_charge_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None, session_date: str, charge: bool,
) -> dict:
    if deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    from datetime import date as _date
    try:
        day = _date.fromisoformat(session_date)
    except ValueError:
        return {"success": False, "data": None,
                "message": "Não entendi a data da sessão. Use AAAA-MM-DD."}
    event = deps.event_service.find_client_session_on_date(deps.user_id, client.id, day)
    if event is None:
        first = client.name.split()[0]
        return {"success": False, "data": None,
                "message": f"Não encontrei sessão de {first} nessa data."}
    deps.event_service.set_billable(event, charge)
    first = client.name.split()[0]
    verb = "vou cobrar" if charge else "não vou cobrar"
    return {"success": True, "data": {"client": client.name, "charge": charge},
            "message": f"Pronto: {verb} a sessão de {first} nessa data."}
```

Register the tool inside `register_calendar_tools`:

```python
    @agent.tool
    async def set_session_charge(
        ctx: RunContext[AgentDeps], session_date: str, charge: bool,
        client_name: str | None = None, client_phone: str | None = None,
    ) -> dict:
        """Define se uma sessão (cancelada/no-show) é cobrável. session_date em AAAA-MM-DD."""
        return await set_session_charge_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            session_date=session_date, charge=charge,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_set_session_charge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/event_service.py app/agents/tools/calendar_tools.py tests/unit/test_set_session_charge.py
git commit -m "feat(agenda): set_session_charge tool to adjust a session's billable"
```

---

### Task 6: Full-suite + lint + migration verification

**Files:** none (verification only).

- [ ] **Step 1:** `uv run pytest -m "not live" -q` — all pass.
- [ ] **Step 2:** `uv run ruff check app tests migrations` — clean on touched files.
- [ ] **Step 3:** `uv run alembic heads` — single head `0010_event_occurrences`.

No commit (verification only).

---

## Self-Review

**Spec coverage:**
- `Event.parent_event_id`/`occurrence_date`/`billable` + unique → Task 1. ✓
- Lazy idempotent materialization → Task 2. ✓
- `list_events` shows occurrences, hides templates + cancelled; `create_event` price → Task 3. ✓
- `cancel_event` charge decision + best-effort Google instance cancel → Task 4. ✓
- `set_session_charge` → Task 5. ✓
- price stamped on occurrences (Task 2) and singles (Task 3). ✓
- No billing logic (3b) introduced. ✓

**Placeholder scan:** no TBD/TODO; every code step shows complete code. The two reviewer-style notes in Tasks 4/5 instruct the implementer to align mocks to the real `_resolve_client` helper names — this is alignment guidance, not a placeholder (the production code is fully specified).

**Type consistency:** `ensure_occurrences(user_id, range_start, range_end) -> int` defined in Task 2, consumed in Tasks 3/4. `cancel_event(event, billable=None)` consistent between Task 4 service + tool. `find_client_session_on_date` / `set_billable` defined and consumed in Task 5. Migration 0010 over 0009, single head. Templates excluded uniformly via `~and_(is_recurring==True, parent_event_id IS NULL)` in Tasks 3 and 5.
