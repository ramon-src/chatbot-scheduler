# Agenda Reschedule, Conflict Detection & Coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reschedule + conflict-warning to the agenda, then cover the whole agenda with deterministic evals (fake calendar) and a real Google live battery.

**Architecture:** Conflict detection and reschedule live in `app/agents/tools/calendar_tools.py` (pure impl + thin `@agent.tool` wrapper); the only service addition is a series re-materialization reset on `EventService`. A test-only `FakeCalendarService` lets the eval harness drive agenda flows deterministically; the live battery verifies the real Google dual-write.

**Tech Stack:** Python 3.11+, Pydantic AI, SQLAlchemy 2, pydantic_evals, pytest, uv.

## Global Constraints

- Código/identificadores/enums em inglês; mensagens ao usuário final em PT-BR.
- Tool contract `{"success": bool, "data": Any, "message": str}`; `message` never contains IDs/JSON/HTML/markdown/URLs.
- Models in schema `simplificapsi`; timezone fixed `America/Sao_Paulo`; week starts Sunday.
- Conflict policy: detect-and-WARN, never block. Create/move anyway; append a plain-text warning when an active event of the professional overlaps `[start, end)`.
- Reschedule scope: single events AND whole recurring series (series = move the series' time-of-day, keep the weekday cadence). Single-occurrence-of-series and weekday changes are OUT of scope.
- Dual-write: Google is source of truth — write Google first; on Google failure degrade with a retry message and do not touch the mirror; never 500 the chat.
- Evals: real LLM, gated `RUN_EVAL=1` + `OPENAI_API_KEY`, default `gpt-5.4-mini`, `evaluate_sync(max_concurrency=1)`. Fake calendar in eval mode — production never imports it.
- Live: gated `RUN_LIVE=1` + service account; uses the existing `live` fixture.
- TDD: new behavior starts with a failing test. No secrets in code. Commits never attribute to AI.

---

### Task 1: Conflict-overlap helper + warn on create

**Files:**
- Modify: `app/agents/tools/calendar_tools.py`
- Test: `tests/unit/test_calendar_conflict.py` (create)

**Interfaces:**
- Consumes: `AgentDeps` (`event_service`, `client_service`, `user_id`, `current_datetime`, `timezone`), `EventService.list_events_in_range(user_id, start, end)`, `EventService.ensure_occurrences(user_id, start, end)`.
- Produces: `_find_overlaps(deps, start, end, *, exclude_event_id=None) -> list[Event]` and `_conflict_warning(deps, conflicts) -> tuple[str, str | None]`, used by Tasks 1 and 3.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_calendar_conflict.py`:

```python
"""Conflict detection: overlap helper + warn-not-block on create."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.tools.calendar_tools import _find_overlaps, create_event_impl

TZ = "America/Sao_Paulo"


def _ev(start, end, client_name="Maria Silva"):
    return SimpleNamespace(
        id=uuid4(), start_time=start, end_time=end,
        client=SimpleNamespace(name=client_name), client_id=uuid4(),
    )


def _deps(events, *, client=None):
    es = MagicMock()
    es.list_events_in_range.return_value = events
    es.ensure_occurrences.return_value = 0
    cs = MagicMock()

    async def _by_name(name, user_id):
        return [client] if client else []

    async def _by_phone(phone, user_id):
        return client

    cs.find_client_by_name = _by_name
    cs.find_client_by_phone = _by_phone
    return SimpleNamespace(
        event_service=es, client_service=cs, calendar_service=MagicMock(),
        user_id=uuid4(), timezone=TZ, default_consult_minutes=60,
        current_datetime=datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo(TZ)),
    )


def test_find_overlaps_detects_overlapping_interval():
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    existing = _ev(base, base + timedelta(minutes=60))
    deps = _deps([existing])
    hits = _find_overlaps(deps, base + timedelta(minutes=30), base + timedelta(minutes=90))
    assert len(hits) == 1


def test_find_overlaps_ignores_adjacent_interval():
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    existing = _ev(base, base + timedelta(minutes=60))
    deps = _deps([existing])
    # new starts exactly when existing ends -> no overlap
    hits = _find_overlaps(deps, base + timedelta(minutes=60), base + timedelta(minutes=120))
    assert hits == []


def test_find_overlaps_excludes_self():
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    existing = _ev(base, base + timedelta(minutes=60))
    deps = _deps([existing])
    hits = _find_overlaps(deps, base, base + timedelta(minutes=60), exclude_event_id=existing.id)
    assert hits == []


@pytest.mark.asyncio
async def test_create_event_warns_on_conflict_but_still_succeeds():
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    existing = _ev(base, base + timedelta(minutes=60), client_name="Maria Silva")
    client = SimpleNamespace(id=uuid4(), name="Ana Souza", consult_price=200)
    deps = _deps([existing], client=client)
    deps.calendar_service.create_event.return_value = {"id": "g-1"}
    deps.event_service.record_event.return_value = SimpleNamespace(id=uuid4())
    out = await create_event_impl(deps, client_name="Ana", start_time=base + timedelta(minutes=30))
    assert out["success"] is True
    assert out["data"].get("conflict") is True
    assert "Atenção" in out["message"]
    assert "Maria" in out["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_calendar_conflict.py -v`
Expected: FAIL — `_find_overlaps` does not exist yet (ImportError).

- [ ] **Step 3: Implement the helpers and wire into create**

In `app/agents/tools/calendar_tools.py`, add near the top helpers (after `_fmt`):

```python
def _day_bounds(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Full-day window spanning [start, end), so list_events_in_range (which filters
    by start_time) catches same-day events regardless of time."""
    from datetime import time
    lo = datetime.combine(start.date(), time.min, tzinfo=start.tzinfo)
    hi = datetime.combine(end.date(), time.max, tzinfo=end.tzinfo)
    return lo, hi


def _find_overlaps(deps: AgentDeps, start: datetime, end: datetime, *, exclude_event_id=None) -> list:
    """Active events of the professional whose [start_time, end_time) overlaps [start, end).
    list_events_in_range already excludes cancelled events and series templates."""
    if deps.event_service is None:
        return []
    lo, hi = _day_bounds(start, end)
    deps.event_service.ensure_occurrences(deps.user_id, lo, hi)
    hits = []
    for e in deps.event_service.list_events_in_range(deps.user_id, lo, hi):
        if exclude_event_id is not None and e.id == exclude_event_id:
            continue
        if e.start_time < end and start < e.end_time:
            hits.append(e)
    return hits


def _conflict_warning(deps: AgentDeps, conflicts: list) -> tuple[str, str | None]:
    """Plain-text warning suffix + the conflicting client's first name (or None)."""
    if not conflicts:
        return "", None
    other = conflicts[0]
    name = other.client.name.split()[0] if getattr(other, "client", None) else "outro cliente"
    return f" Atenção: você já tem {name} nesse horário.", name
```

Then in `create_event_impl`, after `end = start_time + timedelta(minutes=minutes)` and before the Google call, capture conflicts; and replace the success return:

```python
    conflicts = _find_overlaps(deps, start_time, end)

    created = deps.calendar_service.create_event(summary=summary, start=start_time, end=end)
    try:
        deps.event_service.record_event(
            user_id=deps.user_id, client_id=client.id, title=summary,
            start=start_time, end=end, google_event_id=created["id"],
            price=client.consult_price,
        )
    except Exception:
        _compensate_google(deps, created["id"])
        return _dual_write_failed()
    first = client.name.split()[0]
    warning, who = _conflict_warning(deps, conflicts)
    data = {"client": client.name, "start": start_time.isoformat()}
    if who:
        data["conflict"] = True
        data["conflict_with"] = who
    return {"success": True, "data": data,
            "message": f"Agendei {first} para {_fmt(start_time, deps.timezone)}." + warning}
```

Apply the SAME conflict capture + warning to `create_recurring_event_impl`: add `conflicts = _find_overlaps(deps, start_time, end)` before its Google call, and append `warning` to its success message with the same `data` enrichment (compute `warning, who = _conflict_warning(deps, conflicts)` and add `conflict`/`conflict_with` to `data` when `who`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_calendar_conflict.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the calendar unit tests for no regressions**

Run: `uv run pytest tests/unit/test_calendar_tools.py tests/unit/test_calendar_conflict.py -v`
Expected: PASS (existing create/recurring tests still green).

- [ ] **Step 6: Commit**

```bash
git add app/agents/tools/calendar_tools.py tests/unit/test_calendar_conflict.py
git commit -m "feat(agenda): warn when a new appointment overlaps an existing one"
```

---

### Task 2: Extract single-event finder; refactor cancel

**Files:**
- Modify: `app/agents/tools/calendar_tools.py`
- Test: `tests/unit/test_find_single_event.py` (create)

**Interfaces:**
- Consumes: `EventService.ensure_occurrences`, `EventService.list_events_in_range`, `calculate_date_range(period, current_datetime)`.
- Produces: `_find_single_event_for_client(deps, client, period) -> tuple[Event | None, dict | None]` (exactly one non-None), reused by `cancel_event_impl` (this task) and `reschedule_event_impl` (Task 3).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_find_single_event.py`:

```python
"""Shared single-event finder used by cancel and reschedule."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.agents.tools.calendar_tools import _find_single_event_for_client

TZ = "America/Sao_Paulo"


def _deps(events):
    es = MagicMock()
    es.list_events_in_range.return_value = events
    es.ensure_occurrences.return_value = 0
    return SimpleNamespace(
        event_service=es, user_id=uuid4(), timezone=TZ,
        current_datetime=datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo(TZ)),
    )


def test_returns_the_single_matching_event():
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    ev = SimpleNamespace(id=uuid4(), client_id=cid)
    event, error = _find_single_event_for_client(_deps([ev]), client, "this_week")
    assert error is None and event is ev


def test_zero_matches_returns_not_found_error():
    client = SimpleNamespace(id=uuid4(), name="Maria Silva")
    other = SimpleNamespace(id=uuid4(), client_id=uuid4())
    event, error = _find_single_event_for_client(_deps([other]), client, "this_week")
    assert event is None and error["success"] is False and "Maria" in error["message"]


def test_multiple_matches_asks_for_day():
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    evs = [SimpleNamespace(id=uuid4(), client_id=cid), SimpleNamespace(id=uuid4(), client_id=cid)]
    event, error = _find_single_event_for_client(_deps(evs), client, "this_week")
    assert event is None and error["data"]["count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_find_single_event.py -v`
Expected: FAIL — `_find_single_event_for_client` does not exist.

- [ ] **Step 3: Extract the helper and refactor cancel**

Add to `calendar_tools.py`:

```python
def _find_single_event_for_client(deps: AgentDeps, client, period: str):
    """Return (event, error). Exactly one is non-None. Mirrors cancel's resolution:
    0 matches -> not-found; >1 -> ask for the exact day."""
    try:
        start, end = calculate_date_range(period, deps.current_datetime)
    except ValueError:
        return None, {"success": False, "data": None,
                      "message": "Não entendi o período. Tente 'hoje' ou 'esta semana'."}
    deps.event_service.ensure_occurrences(deps.user_id, start, end)
    events = [
        e for e in deps.event_service.list_events_in_range(deps.user_id, start, end)
        if e.client_id == client.id
    ]
    if not events:
        first = client.name.split()[0]
        return None, {"success": False, "data": None,
                      "message": f"Não encontrei compromisso de {first} nesse período."}
    if len(events) > 1:
        return None, {"success": False, "data": {"count": len(events)},
                      "message": "Encontrei mais de um compromisso nesse período. Pode me dizer o dia exato?"}
    return events[0], None
```

Then refactor `cancel_event_impl`: replace the block that computes `start, end`, calls `ensure_occurrences`, filters `events`, and returns the 0/>1 errors with:

```python
    event, error = _find_single_event_for_client(deps, client, period)
    if error:
        return error
```

Leave the rest of `cancel_event_impl` (Google cancel + mirror cancel + success message) unchanged.

- [ ] **Step 4: Run tests to verify pass + no cancel regression**

Run: `uv run pytest tests/unit/test_find_single_event.py tests/unit/test_calendar_tools.py -v`
Expected: PASS (helper tests green; existing cancel tests still green).

- [ ] **Step 5: Commit**

```bash
git add app/agents/tools/calendar_tools.py tests/unit/test_find_single_event.py
git commit -m "refactor(agenda): extract shared single-event finder from cancel"
```

---

### Task 3: Reschedule tool (single + whole series)

**Files:**
- Modify: `app/services/event_service.py` (add `reschedule_series`)
- Modify: `app/agents/tools/calendar_tools.py` (add `reschedule_event_impl` + register `reschedule_event`)
- Test: `tests/unit/test_reschedule_event.py` (create)
- Test: `tests/integration/test_reschedule_series.py` (create)

**Interfaces:**
- Consumes: `_resolve_client`, `_find_single_event_for_client` (Task 2), `_find_overlaps`/`_conflict_warning` (Task 1), `_ensure_aware`, `_fmt`, `EventService.update_event`, `EventService.get_event`, `GoogleCalendarService.update_event(event_id, start=, end=)`.
- Produces: `EventService.reschedule_series(template, new_start, new_end, *, from_dt) -> Event`; `reschedule_event_impl(deps, *, client_name=None, client_phone=None, period="this_week", new_start_time, duration_minutes=None) -> dict`; agent tool `reschedule_event`.

- [ ] **Step 1: Write the failing unit test (single event)**

Create `tests/unit/test_reschedule_event.py`:

```python
"""reschedule_event_impl: single-event move + conflict warning + errors."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.tools.calendar_tools import reschedule_event_impl

TZ = "America/Sao_Paulo"


def _deps(found_event, *, client, overlaps=None):
    es = MagicMock()
    es.ensure_occurrences.return_value = 0
    # _find_single_event_for_client uses list_events_in_range filtered by client_id;
    # _find_overlaps uses it too. Return the client's event for the finder and the
    # overlaps for the conflict scan via side_effect ordering.
    es.list_events_in_range.side_effect = [[found_event], overlaps or []]
    es.update_event.return_value = found_event
    cs = MagicMock()

    async def _by_name(name, user_id):
        return [client]

    async def _by_phone(phone, user_id):
        return client

    cs.find_client_by_name = _by_name
    cs.find_client_by_phone = _by_phone
    return SimpleNamespace(
        event_service=es, client_service=cs, calendar_service=MagicMock(),
        user_id=uuid4(), timezone=TZ, default_consult_minutes=60,
        current_datetime=datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo(TZ)),
    )


@pytest.mark.asyncio
async def test_reschedule_single_updates_both_stores():
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    ev = SimpleNamespace(id=uuid4(), client_id=cid, parent_event_id=None,
                         is_recurring=False, google_event_id="g-1")
    deps = _deps(ev, client=client)
    new_start = datetime(2026, 6, 24, 15, 0, tzinfo=ZoneInfo(TZ))
    out = await reschedule_event_impl(deps, client_name="Maria", new_start_time=new_start)
    assert out["success"] is True
    assert "Remarquei" in out["message"]
    deps.calendar_service.update_event.assert_called_once()
    deps.event_service.update_event.assert_called_once()


@pytest.mark.asyncio
async def test_reschedule_warns_on_conflict():
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    ev = SimpleNamespace(id=uuid4(), client_id=cid, parent_event_id=None,
                         is_recurring=False, google_event_id="g-1")
    overlap = SimpleNamespace(id=uuid4(), client=SimpleNamespace(name="João Souza"),
                              start_time=datetime(2026, 6, 24, 15, 0, tzinfo=ZoneInfo(TZ)),
                              end_time=datetime(2026, 6, 24, 16, 0, tzinfo=ZoneInfo(TZ)))
    deps = _deps(ev, client=client, overlaps=[overlap])
    new_start = datetime(2026, 6, 24, 15, 0, tzinfo=ZoneInfo(TZ))
    out = await reschedule_event_impl(deps, client_name="Maria", new_start_time=new_start)
    assert out["success"] is True
    assert "Atenção" in out["message"] and "João" in out["message"]


@pytest.mark.asyncio
async def test_reschedule_unknown_client_errors():
    cs = MagicMock()

    async def _none_name(name, user_id):
        return []

    cs.find_client_by_name = _none_name
    deps = SimpleNamespace(
        event_service=MagicMock(), client_service=cs, calendar_service=MagicMock(),
        user_id=uuid4(), timezone=TZ, default_consult_minutes=60,
        current_datetime=datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo(TZ)),
    )
    out = await reschedule_event_impl(deps, client_name="Fulano",
                                      new_start_time=datetime(2026, 6, 24, 15, 0, tzinfo=ZoneInfo(TZ)))
    assert out["success"] is False
```

- [ ] **Step 2: Run unit test to verify it fails**

Run: `uv run pytest tests/unit/test_reschedule_event.py -v`
Expected: FAIL — `reschedule_event_impl` does not exist.

- [ ] **Step 3: Add `reschedule_series` to EventService**

In `app/services/event_service.py`, add:

```python
    def reschedule_series(self, template: Event, new_start: datetime, new_end: datetime, *, from_dt: datetime) -> Event:
        """Move a recurring series to a new time-of-day: update the template's
        start/end (the materialization dtstart) and drop future still-scheduled
        occurrences so they re-materialize from the new template. Weekday cadence
        (the RRULE BYDAY) is preserved."""
        template.start_time = new_start
        template.end_time = new_end
        self.db.query(Event).filter(
            and_(
                Event.parent_event_id == template.id,
                Event.status == EventStatus.SCHEDULED.value,
                Event.start_time >= from_dt,
            )
        ).delete(synchronize_session=False)
        self.db.commit()
        self.db.refresh(template)
        return template
```

- [ ] **Step 4: Add `reschedule_event_impl` + register the tool**

In `calendar_tools.py`, add the impl (after `cancel_event_impl`):

```python
async def reschedule_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None,
    period: str = "this_week", new_start_time: datetime, duration_minutes: int | None = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    event, error = _find_single_event_for_client(deps, client, period)
    if error:
        return error

    new_start = _ensure_aware(new_start_time, deps.timezone)
    minutes = duration_minutes or deps.default_consult_minutes
    new_end = new_start + timedelta(minutes=minutes)
    conflicts = _find_overlaps(deps, new_start, new_end, exclude_event_id=event.id)

    is_series = event.parent_event_id is not None or event.is_recurring
    if is_series:
        template = deps.event_service.get_event(event.parent_event_id) if event.parent_event_id else event
        if template is None or not template.google_event_id:
            return _dual_write_failed()
        try:
            deps.calendar_service.update_event(template.google_event_id, start=new_start, end=new_end)
        except Exception:
            return _dual_write_failed()
        deps.event_service.reschedule_series(template, new_start, new_end, from_dt=deps.current_datetime)
    else:
        if not event.google_event_id:
            return _dual_write_failed()
        try:
            deps.calendar_service.update_event(event.google_event_id, start=new_start, end=new_end)
        except Exception:
            return _dual_write_failed()
        deps.event_service.update_event(event, start=new_start, end=new_end)

    first = client.name.split()[0]
    warning, who = _conflict_warning(deps, conflicts)
    data = {"client": client.name, "start": new_start.isoformat()}
    if who:
        data["conflict"] = True
        data["conflict_with"] = who
    return {"success": True, "data": data,
            "message": f"Remarquei {first} para {_fmt(new_start, deps.timezone)}." + warning}
```

Then register the tool inside `register_calendar_tools` (alongside the others):

```python
    @agent.tool
    async def reschedule_event(
        ctx: RunContext[AgentDeps], new_start_time: str,
        client_name: str | None = None, client_phone: str | None = None,
        period: str = "this_week", duration_minutes: int | None = None,
    ) -> dict:
        """Remarca o compromisso de um cliente para um novo horário. new_start_time em ISO 8601.
        Exige cliente cadastrado e um compromisso existente no período."""
        return await reschedule_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            period=period, new_start_time=datetime.fromisoformat(new_start_time),
            duration_minutes=duration_minutes,
        )
```

- [ ] **Step 5: Run unit test to verify pass**

Run: `uv run pytest tests/unit/test_reschedule_event.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Write the failing series integration test**

Create `tests/integration/test_reschedule_series.py` — uses a real DB session to prove the series template moves and future occurrences are dropped. Mirror the existing integration-test setup style in `tests/integration/test_ensure_occurrences.py` for session/user/client/calendar fixtures.

```python
"""reschedule_series moves the template and clears future materialized occurrences."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.event import Event, EventStatus
from app.services.event_service import EventService

TZ = ZoneInfo("America/Sao_Paulo")


def test_reschedule_series_updates_template_and_drops_future(db_session, seed_user_client_calendar):
    user_id, client, calendar = seed_user_client_calendar
    es = EventService(db_session)
    start = datetime(2026, 6, 23, 10, 0, tzinfo=TZ)
    template = es.record_event(
        user_id=user_id, client_id=client.id, title="Sessão - X",
        start=start, end=start + timedelta(minutes=60), google_event_id="g-series",
        is_recurring=True, recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=TU",
    )
    # a future materialized occurrence
    future = Event(
        user_id=user_id, client_id=client.id, calendar_id=calendar.id, title="Sessão - X",
        start_time=start + timedelta(days=7), end_time=start + timedelta(days=7, minutes=60),
        parent_event_id=template.id, occurrence_date=(start + timedelta(days=7)).date(),
        status=EventStatus.SCHEDULED.value,
    )
    db_session.add(future)
    db_session.commit()

    new_start = datetime(2026, 6, 23, 15, 0, tzinfo=TZ)
    es.reschedule_series(template, new_start, new_start + timedelta(minutes=60),
                         from_dt=datetime(2026, 6, 23, 9, 0, tzinfo=TZ))

    db_session.refresh(template)
    assert template.start_time.astimezone(TZ).hour == 15
    remaining = db_session.query(Event).filter(Event.parent_event_id == template.id).count()
    assert remaining == 0
```

If `tests/integration/` lacks reusable `db_session` / `seed_user_client_calendar` fixtures, add them to `tests/integration/conftest.py` following the pattern already used by `test_event_service.py` (read it first; reuse its session + seeding helpers rather than inventing new ones).

- [ ] **Step 7: Run the series integration test**

Run: `uv run pytest tests/integration/test_reschedule_series.py -v`
Expected: PASS.

- [ ] **Step 8: Run agenda-related suites for no regressions**

Run: `uv run pytest tests/unit/test_calendar_tools.py tests/unit/test_reschedule_event.py tests/integration/test_event_service.py tests/integration/test_reschedule_series.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/services/event_service.py app/agents/tools/calendar_tools.py tests/unit/test_reschedule_event.py tests/integration/test_reschedule_series.py
git commit -m "feat(agenda): reschedule_event tool for single and recurring-series appointments"
```

---

### Task 4: FakeCalendarService + agenda-capable eval harness

**Files:**
- Create: `evals/fakes.py`
- Modify: `evals/harness.py`
- Test: `tests/unit/test_fake_calendar.py` (create)
- Test: `tests/integration/test_eval_harness_agenda.py` (create)

**Interfaces:**
- Produces: `FakeCalendarService` (methods `create_event(*, summary, start, end, description=None, recurrence=None) -> {"id": str, "html_link": None}`, `update_event(event_id, **changes) -> dict`, `cancel_event(event_id)`, `cancel_occurrence(series_google_event_id, occurrence_start)`, `list_events(start, end) -> []`, static `build_weekly_rrule(weekdays, until)`); harness `_apply_setup` now seeds an `events` list and a primary `Calendar`; `_snapshot` events include `client` + `start_time`.
- Consumes: `EventService.record_event`, `EventService.get_primary_calendar`, `GoogleCalendarService.build_weekly_rrule`.

- [ ] **Step 1: Write the failing FakeCalendarService test**

Create `tests/unit/test_fake_calendar.py`:

```python
"""FakeCalendarService is deterministic and matches the surface the tools call."""

from evals.fakes import FakeCalendarService


def test_create_event_returns_incrementing_synthetic_ids():
    fake = FakeCalendarService()
    a = fake.create_event(summary="s", start=None, end=None)
    b = fake.create_event(summary="s", start=None, end=None)
    assert a["id"] != b["id"]
    assert a["id"].startswith("fake-")


def test_update_and_cancel_are_noops_returning_expected_shapes():
    fake = FakeCalendarService()
    assert fake.update_event("fake-1", start=None, end=None)["id"] == "fake-1"
    assert fake.cancel_event("fake-1") is None
    assert fake.list_events(None, None) == []


def test_build_weekly_rrule_delegates():
    rule = FakeCalendarService.build_weekly_rrule(["TU"], None)
    assert rule.startswith("RRULE:FREQ=WEEKLY") and "BYDAY=TU" in rule
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_fake_calendar.py -v`
Expected: FAIL — `evals/fakes.py` does not exist.

- [ ] **Step 3: Implement FakeCalendarService**

Create `evals/fakes.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_fake_calendar.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing harness-seeding integration test**

Create `tests/integration/test_eval_harness_agenda.py`:

```python
"""The eval harness can seed a calendar + events and snapshot them with client/time."""

from evals.harness import (
    EVAL_USER_ID, CaseInputs, _apply_setup, _ensure_eval_user, _purge, _snapshot,
)
from app.core.database import SessionLocal


def test_apply_setup_seeds_events_and_snapshot_reports_them():
    db = SessionLocal()
    try:
        _purge(db)
        _ensure_eval_user(db)
        inputs = CaseInputs(agent="pro", messages=[], setup={
            "clients": [{"name": "Maria Silva", "phone": "+5551999990000",
                         "invoice_day": 10, "consult_price": 200}],
            "events": [{"client": "Maria Silva", "start": "2026-06-24T10:00:00-03:00",
                        "duration": 60}],
        })
        _apply_setup(db, inputs)
        snap = _snapshot(db, inputs)
        assert any(e.get("client") and "Maria" in e["client"] for e in snap.events)
        assert any("2026-06-24" in (e.get("start_time") or "") for e in snap.events)
    finally:
        _purge(db)
        db.close()
```

- [ ] **Step 6: Run it to verify it fails**

Run: `RUN_EVAL=1 uv run pytest tests/integration/test_eval_harness_agenda.py -v`
Expected: FAIL — `_apply_setup` does not seed events / `_snapshot` events lack `client`/`start_time`. (If the test is skipped for a missing DB, run with the integration DB up via `make infra`.)

- [ ] **Step 7: Extend the harness**

In `evals/harness.py`:

1. Add `Calendar` purge to `_purge` (after the `Event` delete):

```python
    from app.models.calendar import Calendar
    db.query(Calendar).filter(Calendar.user_id == EVAL_USER_ID).delete(synchronize_session=False)
```

2. In `_apply_setup`, after seeding clients (keep the existing client loop), ensure a primary calendar and seed events:

```python
    from datetime import datetime, timedelta

    from app.services.event_service import EventService
    es = EventService(db)
    es.get_primary_calendar(EVAL_USER_ID)  # ensure a calendar row exists
    seed_events = (inputs.setup or {}).get("events", [])
    if seed_events:
        from app.models.client import Client as _Client
        by_name = {c.name: c for c in db.query(_Client).filter(_Client.user_id == EVAL_USER_ID)}
        for i, ev in enumerate(seed_events):
            client = by_name.get(ev["client"])
            if client is None:
                continue
            start = datetime.fromisoformat(ev["start"])
            end = start + timedelta(minutes=ev.get("duration", 60))
            es.record_event(
                user_id=EVAL_USER_ID, client_id=client.id, title=f"Sessão - {client.name}",
                start=start, end=end, google_event_id=f"seed-{i}",
                is_recurring=bool(ev.get("recurring", False)),
                recurrence_rule=ev.get("recurrence_rule"),
                price=client.consult_price,
            )
```

3. In `_snapshot`, enrich the events list:

```python
    events = [
        {"status": e.status, "billable": e.billable, "is_recurring": e.is_recurring,
         "recurrence_rule": e.recurrence_rule,
         "client": (e.client.name if e.client else None),
         "start_time": e.start_time.isoformat()}
        for e in db.query(Event).filter(Event.user_id == EVAL_USER_ID)
    ]
```

4. In `run_case`, inject the fake calendar for the `pro` agent. Create it once before the loop and override on the deps each turn:

```python
    from evals.fakes import FakeCalendarService
    fake_calendar = FakeCalendarService()
```

and in the `else` (pro) branch inside the loop, right after `deps = build_agent_deps(...)`:

```python
                deps.calendar_service = fake_calendar
```

- [ ] **Step 8: Run the harness integration test + full unit suite**

Run: `RUN_EVAL=1 uv run pytest tests/integration/test_eval_harness_agenda.py -v`
Expected: PASS.

Run: `uv run pytest -p no:warnings -q`
Expected: PASS (no regressions; `test_eval_harness_isolation` and existing harness tests still green).

- [ ] **Step 9: Commit**

```bash
git add evals/fakes.py evals/harness.py tests/unit/test_fake_calendar.py tests/integration/test_eval_harness_agenda.py
git commit -m "feat(evals): fake calendar + agenda-capable eval harness seeding/snapshot"
```

---

### Task 5: Agenda eval dataset + DbState event check + run

**Files:**
- Modify: `evals/evaluators.py` (extend `DbState` with `event_for_client`)
- Create: `evals/datasets/agenda.py`
- Modify: `evals/run.py` (register the agenda suite under `--suite agenda`)
- Modify: `Makefile` (add `eval-agenda` target)
- Test: `tests/unit/test_eval_evaluators.py` (extend with an `event_for_client` case — read the file first to match its style)

**Interfaces:**
- Consumes: `CaseInputs`, `run_case`, `ToolSelected`, `NoLeakage`, `DbState`, `build_eval_model`.
- Produces: `build_agenda_dataset() -> Dataset`; `DbState` check key `event_for_client: <name substr>`.

- [ ] **Step 1: Write the failing evaluator test**

Append to `tests/unit/test_eval_evaluators.py` (match the existing fake-`ctx` style in that file; the snippet below assumes a `DbSnapshot`/`CaseResult` is constructed as the other tests do — reuse their helper):

```python
def test_dbstate_event_for_client_matches_active_event():
    from evals.evaluators import DbState
    from evals.harness import CaseResult, DbSnapshot, Turn  # adjust import to the file's existing pattern
    snap = DbSnapshot(events=[{"status": "scheduled", "client": "Maria Silva", "start_time": "x"}])
    result = CaseResult(tool_calls=[], final_output="", transcript=[], db=snap,
                        tokens=0, latency_ms=0, model="m")
    ctx = type("C", (), {"output": result})()
    assert DbState(check={"event_for_client": "Maria"}).evaluate(ctx) is True
    assert DbState(check={"event_for_client": "Joana"}).evaluate(ctx) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_eval_evaluators.py -k event_for_client -v`
Expected: FAIL — `DbState` does not handle `event_for_client`.

- [ ] **Step 3: Extend DbState**

In `evals/evaluators.py`, inside `DbState.evaluate`, before `return True`, add:

```python
        if "event_for_client" in c:
            name = c["event_for_client"]
            if not any(
                (ev.get("client") or "") and name in ev["client"] and ev.get("status") != "cancelled"
                for ev in db.events
            ):
                return False
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/unit/test_eval_evaluators.py -k event_for_client -v`
Expected: PASS.

- [ ] **Step 5: Create the agenda dataset**

Create `evals/datasets/agenda.py`:

```python
"""Agenda eval cases: schedule, list, cancel, reschedule, conflict-warn (fake calendar)."""

from __future__ import annotations

from pydantic_evals import Case, Dataset

from evals.evaluators import DbState, NoLeakage, ToolSelected
from evals.harness import CaseInputs

_MARIA = {"clients": [
    {"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10, "consult_price": 200},
]}
_MARIA_WITH_EVENT = {
    "clients": _MARIA["clients"],
    "events": [{"client": "Maria Silva", "start": "2026-06-24T10:00:00-03:00", "duration": 60}],
}
_TWO = {"clients": [
    {"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10, "consult_price": 200},
    {"name": "Joao Souza", "phone": "+5551988887777", "invoice_day": 5, "consult_price": 180},
]}


def build_agenda_dataset() -> Dataset:
    cases = [
        Case(
            name="agenda_marca_unico",
            inputs=CaseInputs(agent="pro", setup=_MARIA,
                              messages=["agenda a Maria Silva amanhã às 10h"]),
            evaluators=[ToolSelected(tool="create_event"),
                        DbState(check={"event_for_client": "Maria"}), NoLeakage()],
        ),
        Case(
            name="agenda_lista_periodo",
            inputs=CaseInputs(agent="pro", setup=_MARIA_WITH_EVENT,
                              messages=["o que tenho essa semana?"]),
            evaluators=[ToolSelected(tool="list_events"), NoLeakage()],
        ),
        Case(
            name="agenda_lista_vazia",
            inputs=CaseInputs(agent="pro", setup=_MARIA,
                              messages=["tenho algo agendado hoje?"]),
            evaluators=[ToolSelected(tool="list_events"), NoLeakage()],
        ),
        Case(
            name="agenda_cancela",
            inputs=CaseInputs(agent="pro", setup=_MARIA_WITH_EVENT,
                              messages=["cancela o compromisso da Maria Silva dessa semana"]),
            evaluators=[ToolSelected(tool="cancel_event"), NoLeakage()],
        ),
        Case(
            name="agenda_reagenda",
            inputs=CaseInputs(agent="pro", setup=_MARIA_WITH_EVENT,
                              messages=["muda o compromisso da Maria Silva dessa semana para as 15h"]),
            evaluators=[ToolSelected(tool="reschedule_event"), NoLeakage()],
        ),
        Case(
            name="agenda_conflito_avisa",  # warn-not-block: the 2nd event still gets created
            inputs=CaseInputs(agent="pro", setup=_MARIA_WITH_EVENT,
                              messages=["cadastra o João Souza, telefone 51 98888-7777, dia 5, 180 reais",
                                        "agenda o João Souza quarta que vem às 10h"]),
            evaluators=[ToolSelected(tool="create_event"),
                        DbState(check={"event_for_client": "João"}), NoLeakage()],
        ),
        Case(
            name="agenda_homonimo_pede_telefone",
            inputs=CaseInputs(agent="pro", setup=_TWO,
                              messages=["agenda a Maria amanhã às 11h"]),
            evaluators=[NoLeakage()],
        ),
    ]
    return Dataset(name="agenda", cases=cases)
```

- [ ] **Step 6: Register the agenda suite in the runner**

In `evals/run.py`, extend the suite selection so `--suite agenda` builds `build_agenda_dataset()` with the agent task (same `run_case` task as the default agent suite). Add an `elif suite == "agenda":` branch that imports `from evals.datasets.agenda import build_agenda_dataset`, sets `dataset = build_agenda_dataset()`, and reuses the `run_case`-based `task` (identical to the `else` branch). Update the argparse `--suite` `choices` to include `"agenda"`.

- [ ] **Step 7: Add the Makefile target**

After `eval-summary`, add:

```makefile
eval-agenda: ## Rodar o eval de agenda (LLM real + calendário fake; usage: make eval-agenda [MODEL=gpt-5.4-mini] [CASE=<substr>])
	@RUN_EVAL=1 $(UV) run python -m evals.run --suite agenda --model $(or $(MODEL),gpt-5.4-mini) $(if $(CASE),--case $(CASE),)
```

- [ ] **Step 8: Run the unit suite (deterministic gate)**

Run: `uv run pytest -p no:warnings -q`
Expected: PASS.

- [ ] **Step 9: Run the real agenda eval (behavioral gate)**

Run: `make eval-agenda`
Expected: the agenda suite runs against `gpt-5.4-mini`; record per-case PASS/FAIL verbatim in the report. Do NOT weaken any assertion to make a case pass — a model/tool gap is a real finding. (Needs `OPENAI_API_KEY`; the target sets `RUN_EVAL=1`.)

- [ ] **Step 10: Commit**

```bash
git add evals/evaluators.py evals/datasets/agenda.py evals/run.py Makefile tests/unit/test_eval_evaluators.py
git commit -m "feat(evals): agenda suite (schedule/list/cancel/reschedule/conflict) + event DbState check"
```

---

### Task 6: Live persistence battery (real Google)

**Files:**
- Modify: `tests/live/test_agent_live_scenarios.py` (un-skip READY + the two now-built FEATURE scenarios)
- Create: `tests/live/test_agent_live_persistence.py`

**Interfaces:**
- Consumes: the `live` fixture (`tests/live/conftest.py`): `live.send`, `live.send_memory` (if present), `live.db`, `live.tool_returns`, `live.tz`, `live.user_id`, `live.client_name`, `live.client_phone`.

- [ ] **Step 1: Enable READY agenda scenarios**

In `tests/live/test_agent_live_scenarios.py`, remove the `@pytest.mark.skip(...)` decorators on: `test_schedule_with_explicit_duration`, `test_list_empty_period_says_so`, `test_homonym_requires_phone`, `test_cancel_ambiguous_asks_for_day`. Leave their bodies as written.

- [ ] **Step 2: Enable + adjust the now-built FEATURE scenarios**

Un-skip `test_reschedule_event` and `test_conflict_detection_warns`. Read each body; update assertions to match the shipped behavior:
- reschedule: assert the agent called `reschedule_event` (via `live.tool_returns(result, "reschedule_event")`) and the success message says "Remarquei".
- conflict: warn-not-block — assert the overlapping event WAS still created (the create tool returned `success: True`) and the reply contains "Atenção". Do not assert a refusal.

If a body references a tool/behavior that does not match Task 1/3's actual return shape, fix the assertion to the real shape (do not change product code from here).

- [ ] **Step 3: Write the persistence round-trip module**

Create `tests/live/test_agent_live_persistence.py`. Read `tests/live/test_agent_live.py` first to copy the exact `live` fixture usage and helpers. Cover three round-trips:

```python
"""Live persistence round-trips: create/list/cancel/reschedule reflect in both stores."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_created_event_persists_and_lists_back(live):
    await live.send(f"agenda a {live.client_name} amanhã às 14h")
    # mirror has it
    from app.models.event import Event, EventStatus
    rows = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status == EventStatus.SCHEDULED.value
    ).all()
    assert any(r.start_time.astimezone(live.tz).hour == 14 for r in rows)
    # agent lists it back at the right local time
    listed = await live.send("o que tenho amanhã?")
    assert "14" in listed.output


async def test_cancel_removes_from_both_stores(live):
    await live.send(f"agenda a {live.client_name} amanhã às 9h")
    await live.send(f"cancela o compromisso da {live.client_name} amanhã")
    from app.models.event import Event, EventStatus
    active = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status == EventStatus.SCHEDULED.value,
    ).all()
    assert all(r.start_time.astimezone(live.tz).hour != 9 for r in active)


async def test_reschedule_reflects_new_time(live):
    await live.send(f"agenda a {live.client_name} amanhã às 11h")
    await live.send(f"muda o compromisso da {live.client_name} amanhã para as 16h")
    from app.models.event import Event, EventStatus
    rows = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status == EventStatus.SCHEDULED.value,
    ).all()
    hours = {r.start_time.astimezone(live.tz).hour for r in rows}
    assert 16 in hours and 11 not in hours
```

If the `live` fixture's `send` does not persist across calls within a test (each call independent), use `live.send_memory` where multi-turn continuity matters (cancel/reschedule reference a prior create) — check the fixture in `conftest.py` and pick the helper that replays history.

- [ ] **Step 4: Collect the live tests (no run) to verify they import/parse**

Run: `uv run pytest tests/live/test_agent_live_persistence.py tests/live/test_agent_live_scenarios.py --collect-only -q`
Expected: tests are collected with no import/parse errors. (Without `RUN_LIVE=1` they will skip at runtime — collection still validates the code.)

- [ ] **Step 5: Run the full non-live suite for no regressions**

Run: `uv run pytest -p no:warnings -q`
Expected: PASS (live tests skip without `RUN_LIVE`).

- [ ] **Step 6: Commit**

```bash
git add tests/live/test_agent_live_scenarios.py tests/live/test_agent_live_persistence.py
git commit -m "test(agenda): enable READY live scenarios + persistence round-trips"
```

- [ ] **Step 7: Run the live battery (real Google + OpenAI)**

Run: `RUN_LIVE=1 uv run pytest tests/live -p no:warnings -v`
Expected: the agenda live scenarios + persistence round-trips run against the real service account and OpenAI. Record per-test PASS/FAIL verbatim in the report. If credentials are unavailable in this environment, report that the controller must run it; do NOT mark the task done on green collection alone — the live run is the behavioral gate. Do not weaken assertions to pass.

---

## Self-Review

**Spec coverage:**
- Conflict detection (warn, professional-overlap window) → Task 1 (`_find_overlaps`, `_conflict_warning`, wired into create + recurring), reschedule conflict → Task 3.
- Reschedule single + whole series → Task 3 (`reschedule_event_impl` + `EventService.reschedule_series`); shared finder → Task 2.
- Fake-calendar eval support (inject, seed calendar+events, snapshot time/client) → Task 4.
- Agenda eval cases (schedule/list/empty/cancel/reschedule/conflict/homonym) + DbState event check + run → Task 5.
- Live: enable READY → Task 6 Step 1; enable reschedule/conflict → Step 2; persistence round-trips → Step 3; run battery → Step 7.
- Out-of-scope (single-occurrence reschedule, weekday change, block policy, billing) → not implemented; series reschedule explicitly moves time-of-day only.

**Placeholder scan:** none — every code step shows full content. Two steps say "read the existing file first to match fixture/style" (Task 3 Step 6, Task 5 Step 1, Task 6 Step 3) — these are concrete instructions to reuse existing patterns, not deferred work; the test bodies are fully specified.

**Type consistency:** `_find_overlaps(deps, start, end, *, exclude_event_id=None)`, `_conflict_warning(deps, conflicts) -> (str, str|None)`, `_find_single_event_for_client(deps, client, period) -> (event|None, dict|None)`, `reschedule_event_impl(deps, *, client_name, client_phone, period, new_start_time, duration_minutes)`, `EventService.reschedule_series(template, new_start, new_end, *, from_dt)`, `FakeCalendarService.create_event(*, summary, start, end, description=None, recurrence=None)`, `DbState` key `event_for_client` — all consistent between definition and use. Tool name `reschedule_event` consistent across Task 3 (register), Task 5 (eval `ToolSelected`), Task 6 (live assertions).
