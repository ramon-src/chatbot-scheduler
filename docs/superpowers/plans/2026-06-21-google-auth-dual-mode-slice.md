# Google Auth Dual-Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a service-account auth mode (the zero-friction default: events go to a per-professional calendar created under our service account) alongside the existing per-user OAuth mode (opt-in: events go to the professional's own Google Calendar), selected per user at request time.

**Architecture:** A resolver (`calendar_provider.build_calendar_access`) picks the mode per user: OAuth credentials present → use the professional's `primary` calendar; else service account configured → find-or-create a calendar for the professional under the SA (best-effort ACL share with their email) and use it; else → not connected (graceful degrade). The Google API resource is injected, so tests never hit the network.

**Tech Stack:** Python 3.11+ · `google-auth` (`service_account.Credentials`) · `google-api-python-client` · SQLAlchemy 2 · FastAPI · pytest. Builds on the agenda slice (`feat/agenda-google-calendar`).

## Global Constraints

- Code/identifiers in **English**; user-facing `message` in **PT-BR**.
- Tool contract unchanged: `{success,data,message}`; `message` **never** leaks IDs/URLs — the real `google_calendar_id` (e.g. `…@group.calendar.google.com`) must never appear in any `message`.
- All models in schema `simplificapsi`.
- **Tests never hit the Google network** — inject the API resource / mock credential builders.
- OAuth, when present, **takes priority** over the service account. An OAuth user whose token is broken → not connected (do NOT silently fall back to SA — would split their events across calendars).
- Service-account credentials come from `GOOGLE_CLIENT_EMAIL` + `GOOGLE_PRIVATE_KEY` (`.env`), private key with escaped `\n` → `.replace("\\n", "\n")`. Scope: `https://www.googleapis.com/auth/calendar`.
- **No secrets in git.** No AI attribution in commits. Do not invent model IDs.
- TDD: red→green, one commit per task.

Spec: `docs/superpowers/specs/2026-06-21-google-auth-dual-mode-design.md`

---

## File Structure

- Modify `app/core/config.py` — add `GOOGLE_CLIENT_EMAIL`, `GOOGLE_PRIVATE_KEY`.
- Modify `app/services/google_auth.py` — add `service_account_available`, `build_service_account_credentials`, `GOOGLE_CALENDAR_SCOPES`.
- Modify `app/services/google_calendar_service.py` — keep the resource; add `create_calendar`, `share_calendar`.
- Modify `app/services/event_service.py` — add `get_existing_primary`, `ensure_calendar`.
- Create `app/services/calendar_provider.py` — `CalendarAccess` + `build_calendar_access`.
- Modify `app/api/agent_routes.py` — use the provider; load the `User` for name/email.
- Modify `env.example`, `CLAUDE.md` — document dual-mode + new env vars.
- Tests under `tests/unit/` and `tests/integration/`.

---

### Task 1: Service-account credentials builder + config

**Files:**
- Modify: `app/core/config.py` (GOOGLE CALENDAR section, ~line 64-69)
- Modify: `app/services/google_auth.py`
- Test: `tests/unit/test_service_account_auth.py`

**Interfaces:**
- Produces in `google_auth.py`:
  - `GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]`
  - `service_account_available(settings) -> bool` — True iff both `GOOGLE_CLIENT_EMAIL` and `GOOGLE_PRIVATE_KEY` are set on `settings`.
  - `build_service_account_credentials(settings) -> Credentials | None` — None when unavailable; else `service_account.Credentials.from_service_account_info({...}, scopes=GOOGLE_CALENDAR_SCOPES)` with the private key's `\n` un-escaped. Must reference the module attribute `google_auth.service_account` so tests can monkeypatch it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_service_account_auth.py
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import google_auth
from app.services.google_auth import build_service_account_credentials, service_account_available


def _settings(email="sa@x.iam.gserviceaccount.com", key="-----BEGIN-----\\nabc\\n-----END-----"):
    return SimpleNamespace(GOOGLE_CLIENT_EMAIL=email, GOOGLE_PRIVATE_KEY=key)


def test_available_true_when_both_set():
    assert service_account_available(_settings()) is True


def test_available_false_when_missing():
    assert service_account_available(_settings(email=None)) is False
    assert service_account_available(_settings(key=None)) is False


def test_build_returns_none_when_unavailable():
    assert build_service_account_credentials(_settings(email="")) is None


def test_build_unescapes_newlines_and_sets_scope(monkeypatch):
    captured = {}

    class FakeSA:
        class Credentials:
            @staticmethod
            def from_service_account_info(info, scopes=None):
                captured["info"] = info
                captured["scopes"] = scopes
                return MagicMock(name="sa-credentials")

    monkeypatch.setattr(google_auth, "service_account", FakeSA)
    creds = build_service_account_credentials(_settings())
    assert creds is not None
    assert captured["info"]["client_email"] == "sa@x.iam.gserviceaccount.com"
    assert "\\n" not in captured["info"]["private_key"]  # un-escaped to real newlines
    assert "\n" in captured["info"]["private_key"]
    assert captured["scopes"] == ["https://www.googleapis.com/auth/calendar"]
    assert captured["info"]["token_uri"] == "https://oauth2.googleapis.com/token"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_service_account_auth.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_service_account_credentials'`

- [ ] **Step 3: Add config fields**

In `app/core/config.py`, in the GOOGLE CALENDAR section (after `GOOGLE_SCOPES`), add:
```python
    GOOGLE_CLIENT_EMAIL: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_EMAIL")
    GOOGLE_PRIVATE_KEY: Optional[str] = Field(default=None, env="GOOGLE_PRIVATE_KEY")
```

- [ ] **Step 4: Implement in `google_auth.py`**

Add the import and functions:
```python
from google.oauth2 import service_account  # add near the other google imports

GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def service_account_available(settings) -> bool:
    return bool(
        getattr(settings, "GOOGLE_CLIENT_EMAIL", None)
        and getattr(settings, "GOOGLE_PRIVATE_KEY", None)
    )


def build_service_account_credentials(settings):
    """Build server-to-server (JWT) credentials from the SA env vars, or None."""
    if not service_account_available(settings):
        return None
    info = {
        "type": "service_account",
        "client_email": settings.GOOGLE_CLIENT_EMAIL,
        "private_key": settings.GOOGLE_PRIVATE_KEY.replace("\\n", "\n"),
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return service_account.Credentials.from_service_account_info(info, scopes=GOOGLE_CALENDAR_SCOPES)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_service_account_auth.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py app/services/google_auth.py tests/unit/test_service_account_auth.py
git commit -m "feat(auth): build service-account credentials from env (zero-friction default)"
```

---

### Task 2: `GoogleCalendarService.create_calendar` + `share_calendar`

**Files:**
- Modify: `app/services/google_calendar_service.py`
- Test: `tests/unit/test_google_calendar_service.py` (extend)

**Interfaces:**
- `__init__` must retain the resource (`self._resource = resource`) in addition to `self._events`.
- `create_calendar(summary: str) -> dict` → `self._resource.calendars().insert(body={"summary", "timeZone": self._tz}).execute()`; returns `{"id": created["id"]}`.
- `share_calendar(calendar_id: str, email: str, role: str = "writer") -> None` → `self._resource.acl().insert(calendarId=calendar_id, body={"role": role, "scope": {"type": "user", "value": email}}).execute()`.

- [ ] **Step 1: Write the failing test** (append to the existing file)

```python
def test_create_calendar_inserts_and_returns_id():
    resource = MagicMock()
    resource.calendars.return_value.insert.return_value.execute.return_value = {"id": "cal-xyz@group.calendar.google.com"}
    svc = GoogleCalendarService(resource, timezone="America/Sao_Paulo")
    out = svc.create_calendar("SimplificaPsi — Dra. Ana")
    assert out["id"] == "cal-xyz@group.calendar.google.com"
    body = resource.calendars.return_value.insert.call_args.kwargs["body"]
    assert body["summary"] == "SimplificaPsi — Dra. Ana"
    assert body["timeZone"] == "America/Sao_Paulo"


def test_share_calendar_inserts_acl_writer_rule():
    resource = MagicMock()
    svc = GoogleCalendarService(resource, timezone="America/Sao_Paulo")
    svc.share_calendar("cal-1", "ana@gmail.com")
    kwargs = resource.acl.return_value.insert.call_args.kwargs
    assert kwargs["calendarId"] == "cal-1"
    assert kwargs["body"]["role"] == "writer"
    assert kwargs["body"]["scope"] == {"type": "user", "value": "ana@gmail.com"}
    resource.acl.return_value.insert.return_value.execute.assert_called_once()
```

Note: the existing tests build the service via a helper `_service_with_events(events_mock)` that sets `resource.events.return_value = events_mock`. These two new tests construct `GoogleCalendarService(resource, ...)` directly with a fresh `MagicMock()` resource — fine, because `__init__` will call `resource.events()` (returns a MagicMock) and also store `resource`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_google_calendar_service.py -v`
Expected: FAIL with `AttributeError: 'GoogleCalendarService' object has no attribute 'create_calendar'`

- [ ] **Step 3: Implement**

In `__init__`, add `self._resource = resource` (keep the existing `self._events = resource.events()`). Then add the methods:
```python
    def create_calendar(self, summary: str) -> dict:
        body = {"summary": summary, "timeZone": self._tz}
        created = self._resource.calendars().insert(body=body).execute()
        return {"id": created["id"]}

    def share_calendar(self, calendar_id: str, email: str, role: str = "writer") -> None:
        self._resource.acl().insert(
            calendarId=calendar_id,
            body={"role": role, "scope": {"type": "user", "value": email}},
        ).execute()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_google_calendar_service.py -v`
Expected: PASS (existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add app/services/google_calendar_service.py tests/unit/test_google_calendar_service.py
git commit -m "feat(auth): GoogleCalendarService can create + share calendars (SA mode)"
```

---

### Task 3: `EventService.ensure_calendar` + `get_existing_primary`

**Files:**
- Modify: `app/services/event_service.py`
- Test: `tests/integration/test_event_service.py` (extend)

**Interfaces:**
- `get_existing_primary(user_id: UUID) -> Calendar | None` — read-only; the user's `is_primary` calendar or None.
- `ensure_calendar(user_id: UUID, google_calendar_id: str, name: str = "Principal") -> Calendar` — upsert the user's primary calendar row, setting `google_calendar_id` (and `name`); commit; return it. Creates with `is_primary=True, is_active=True` when absent, else updates the existing row's `google_calendar_id`/`name`.

- [ ] **Step 1: Write the failing test** (append; reuse the file's `db` fixture and `DEV_USER_ID`)

```python
def test_ensure_calendar_creates_then_updates(db):
    from app.models.calendar import Calendar
    # cleanup any pre-existing primary for a clean assertion
    db.query(Calendar).filter(Calendar.user_id == DEV_USER_ID, Calendar.is_primary == True).delete(synchronize_session=False)  # noqa: E712
    db.commit()
    svc = EventService(db)
    assert svc.get_existing_primary(DEV_USER_ID) is None
    cal = svc.ensure_calendar(DEV_USER_ID, "sa-cal-1@group.calendar.google.com", name="SimplificaPsi — Dev")
    assert cal.google_calendar_id == "sa-cal-1@group.calendar.google.com"
    assert cal.is_primary is True
    # second call updates the SAME row (no duplicate)
    cal2 = svc.ensure_calendar(DEV_USER_ID, "sa-cal-2@group.calendar.google.com")
    assert cal2.id == cal.id
    assert cal2.google_calendar_id == "sa-cal-2@group.calendar.google.com"
    # restore the default primary so other tests/seed stay consistent
    svc.ensure_calendar(DEV_USER_ID, "primary", name="Principal")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make infra && make migrate && make seed && uv run pytest tests/integration/test_event_service.py -v`
Expected: FAIL with `AttributeError: 'EventService' object has no attribute 'ensure_calendar'`

- [ ] **Step 3: Implement** (add to `EventService`)

```python
    def get_existing_primary(self, user_id: UUID) -> Calendar | None:
        return self.db.query(Calendar).filter(
            and_(Calendar.user_id == user_id, Calendar.is_primary == True)  # noqa: E712
        ).first()

    def ensure_calendar(self, user_id: UUID, google_calendar_id: str, name: str = "Principal") -> Calendar:
        cal = self.get_existing_primary(user_id)
        if cal is None:
            cal = Calendar(
                user_id=user_id, name=name, google_calendar_id=google_calendar_id,
                is_primary=True, is_active=True,
            )
            self.db.add(cal)
        else:
            cal.google_calendar_id = google_calendar_id
            cal.name = name
        self.db.commit()
        self.db.refresh(cal)
        return cal
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_event_service.py -v`
Expected: PASS (existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add app/services/event_service.py tests/integration/test_event_service.py
git commit -m "feat(auth): EventService.ensure_calendar upserts the real google_calendar_id"
```

---

### Task 4: `calendar_provider.build_calendar_access` (the resolver)

**Files:**
- Create: `app/services/calendar_provider.py`
- Test: `tests/unit/test_calendar_provider.py`

**Interfaces:**
- `@dataclass CalendarAccess: service: GoogleCalendarService; calendar: Calendar`
- `build_calendar_access(db, user, settings, *, build_resource=None, event_service=None) -> CalendarAccess | None`
  - `user` is the SQLAlchemy `User` (needs `.id`, `.name`, `.email`).
  - `build_resource` is an injectable `Callable[[credentials], resource]` (defaults to a googleapiclient `build` wrapper) — so tests never import googleapiclient.
  - Logic:
    1. **OAuth priority:** if `has_credentials(db, user.id)` → `creds = load_credentials(...)`, `resource = build_resource(creds)`, `cal = event_service.ensure_calendar(user.id, "primary")`, return `CalendarAccess(GoogleCalendarService(resource, tz, calendar_id="primary"), cal)`. If anything in this branch raises → return `None` (do NOT fall back to SA).
    2. **SA default:** `sa = build_service_account_credentials(settings)`; if `None` → return `None`. Else `resource = build_resource(sa)`, `svc = GoogleCalendarService(resource, tz)`. If `get_existing_primary(user.id)` has a real id (non-null and `!= "primary"`) → reuse it. Else `created = svc.create_calendar(f"SimplificaPsi — {user.name}")`, best-effort `svc.share_calendar(created["id"], user.email)` when `user.email` (swallow share failures), then `cal = event_service.ensure_calendar(user.id, created["id"], name=…)`. Return `CalendarAccess(GoogleCalendarService(resource, tz, calendar_id=cal.google_calendar_id), cal)`. Any unexpected failure in this branch → `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_calendar_provider.py
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services import calendar_provider
from app.services.calendar_provider import build_calendar_access


def _user(name="Dra. Ana", email="ana@gmail.com"):
    return SimpleNamespace(id=uuid4(), name=name, email=email)


def _settings():
    return SimpleNamespace(TIMEZONE="America/Sao_Paulo",
                           GOOGLE_CLIENT_EMAIL="sa@x.iam", GOOGLE_PRIVATE_KEY="k")


def _es(existing=None):
    es = MagicMock()
    es.get_existing_primary.return_value = existing
    es.ensure_calendar.side_effect = lambda uid, gcid, name="Principal": SimpleNamespace(
        id=uuid4(), user_id=uid, google_calendar_id=gcid, name=name, is_primary=True
    )
    return es


def test_oauth_takes_priority(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: True)
    monkeypatch.setattr(calendar_provider, "load_credentials", lambda db, uid: MagicMock())
    es = _es()
    access = build_calendar_access(
        MagicMock(), _user(), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None
    assert access.calendar.google_calendar_id == "primary"
    es.ensure_calendar.assert_called_once()
    assert es.ensure_calendar.call_args.args[1] == "primary"  # ensure_calendar(user_id, "primary")


def test_sa_default_creates_and_shares_calendar(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    fake_sa_creds = object()
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: fake_sa_creds)

    created_service = MagicMock()
    created_service.create_calendar.return_value = {"id": "sa-cal@group.calendar.google.com"}
    monkeypatch.setattr(calendar_provider, "GoogleCalendarService", lambda resource, tz, calendar_id=None: created_service)

    es = _es(existing=None)
    access = build_calendar_access(
        MagicMock(), _user(email="ana@gmail.com"), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None
    created_service.create_calendar.assert_called_once()
    created_service.share_calendar.assert_called_once_with("sa-cal@group.calendar.google.com", "ana@gmail.com")
    es.ensure_calendar.assert_called_once()
    assert es.ensure_calendar.call_args.args[1] == "sa-cal@group.calendar.google.com"


def test_sa_reuses_existing_calendar(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: object())
    svc = MagicMock()
    monkeypatch.setattr(calendar_provider, "GoogleCalendarService", lambda resource, tz, calendar_id=None: svc)
    existing = SimpleNamespace(id=uuid4(), google_calendar_id="old-cal@group.calendar.google.com", is_primary=True)
    es = _es(existing=existing)
    access = build_calendar_access(
        MagicMock(), _user(), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None
    svc.create_calendar.assert_not_called()  # reused, not recreated


def test_share_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: object())
    svc = MagicMock()
    svc.create_calendar.return_value = {"id": "sa-cal"}
    svc.share_calendar.side_effect = RuntimeError("not a google account")
    monkeypatch.setattr(calendar_provider, "GoogleCalendarService", lambda resource, tz, calendar_id=None: svc)
    es = _es(existing=None)
    access = build_calendar_access(
        MagicMock(), _user(email="x@x.com"), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None  # share failure does not break scheduling


def test_no_credentials_and_no_sa_returns_none(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: None)
    access = build_calendar_access(
        MagicMock(), _user(), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=_es(),
    )
    assert access is None


def test_no_share_when_user_has_no_email(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: object())
    svc = MagicMock()
    svc.create_calendar.return_value = {"id": "sa-cal"}
    monkeypatch.setattr(calendar_provider, "GoogleCalendarService", lambda resource, tz, calendar_id=None: svc)
    es = _es(existing=None)
    access = build_calendar_access(
        MagicMock(), _user(email=None), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None
    svc.share_calendar.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_calendar_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.calendar_provider`

- [ ] **Step 3: Implement `calendar_provider.py`**

```python
# app/services/calendar_provider.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_calendar_provider.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/calendar_provider.py tests/unit/test_calendar_provider.py
git commit -m "feat(auth): calendar_provider resolves SA-default vs OAuth-opt-in per user"
```

---

### Task 5: Wire the provider into the route + docs

**Files:**
- Modify: `app/api/agent_routes.py`
- Modify: `tests/integration/test_agent_message_endpoint.py`
- Modify: `env.example`, `CLAUDE.md`
- Test: `tests/unit/test_agent_route_calendar_wiring.py`

**Interfaces:**
- The route loads the `User` (`db.get(User, user_id)`) for name/email, calls `build_calendar_access(db, user, settings)` (guarded so it never 500s), passes `access.service` (or `None`) and `EventService(db)` into `AgentDeps`, and sets `user_name=user.name`.

- [ ] **Step 1: Write the failing unit test**

```python
# tests/unit/test_agent_route_calendar_wiring.py
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.api import agent_routes


def test_route_uses_calendar_provider(monkeypatch):
    """The route must resolve calendar access via build_calendar_access and tolerate None."""
    sentinel_service = object()
    user = SimpleNamespace(id=uuid4(), name="Dra. Ana", email="ana@gmail.com")

    captured = {}
    monkeypatch.setattr(agent_routes, "build_calendar_access",
                        lambda db, u, s: SimpleNamespace(service=sentinel_service, calendar=None))

    # build_deps is the helper under test; if implemented inline, expose it.
    deps = agent_routes._build_agent_deps(db=MagicMock(), user=user)
    assert deps.calendar_service is sentinel_service
    assert deps.user_name == "Dra. Ana"


def test_route_handles_no_calendar_access(monkeypatch):
    user = SimpleNamespace(id=uuid4(), name="Dr. Bob", email=None)
    monkeypatch.setattr(agent_routes, "build_calendar_access", lambda db, u, s: None)
    deps = agent_routes._build_agent_deps(db=MagicMock(), user=user)
    assert deps.calendar_service is None
    assert deps.user_name == "Dr. Bob"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agent_route_calendar_wiring.py -v`
Expected: FAIL (`_build_agent_deps` / `build_calendar_access` not in agent_routes)

- [ ] **Step 3: Refactor the route to use the provider**

Replace the body of `agent_routes.py` from the imports down. Extract a `_build_agent_deps(db, user)` helper (so it's unit-testable) and call the provider:
```python
from app.models.user import User
from app.services.calendar_provider import build_calendar_access
# (remove the now-unused has_credentials/load_credentials/GoogleCalendarService inline imports)


def _build_agent_deps(db: Session, user) -> AgentDeps:
    access = None
    try:
        access = build_calendar_access(db, user, settings)
    except Exception:  # noqa: BLE001 - never 500 the chat on calendar setup
        access = None
    return AgentDeps(
        db=db,
        user_id=user.id,
        user_name=user.name,
        current_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
        timezone=settings.TIMEZONE,
        history_summary=None,
        client_service=ClientService(db),
        calendar_service=access.service if access else None,
        event_service=EventService(db),
    )


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest, db: Session = Depends(get_db)):
    agent = build_simplifica_agent()
    user = db.get(User, payload.user_id)
    if user is None:
        # unknown user: run with no calendar/user context (client tools still work via user_id)
        user = User(id=payload.user_id, name="profissional", email=None)
    deps = _build_agent_deps(db, user)
    result = await agent.run(payload.message, deps=deps)
    return AgentMessageResponse(content=result.output)
```
Keep `user_id` as `user.id` (a real `User` or the fallback stub both have `.id`).

- [ ] **Step 4: Keep the existing endpoint integration test hermetic**

In `tests/integration/test_agent_message_endpoint.py`, the mocked `get_db` returns a `MagicMock`, so `db.get(User, ...)` returns a truthy mock and `build_calendar_access` would run against mocks. Add a monkeypatch so the endpoint test stays network-free and deterministic:
```python
    monkeypatch.setattr(agent_routes, "build_calendar_access", lambda db, user, settings: None)
```
Place it next to the existing `monkeypatch.setattr(agent_routes, "ClientService", ...)`. Also ensure `db.get` returns something with `.id/.name/.email`: since `get_db` is overridden to `MagicMock()`, `db.get(...)` yields a MagicMock (truthy, attribute access returns mocks) — acceptable because `build_calendar_access` is now stubbed to `None` and `user.name` is a MagicMock (coerced to str by AgentDeps typing at runtime is fine; the response only asserts `content`). If the test asserts on `user_name`, leave it; otherwise no change needed.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_agent_route_calendar_wiring.py tests/integration/test_agent_message_endpoint.py -v`
Expected: PASS (2 new + existing endpoint test green)

- [ ] **Step 6: Docs — env.example + CLAUDE.md**

In `env.example`, under the Google section, add:
```
# Service Account (modo padrão, fricção zero — cria calendário sob a SA):
GOOGLE_CLIENT_EMAIL=
GOOGLE_PRIVATE_KEY=
# OAuth de usuário (upgrade opcional — agenda pessoal do profissional):
# GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET já existem acima.
```

In `CLAUDE.md` §2 (decisões) or §7 (atenção), add a bullet:
```
- **Auth Google é dual-mode (decisão).** Padrão = **service account** (`GOOGLE_CLIENT_EMAIL`+`GOOGLE_PRIVATE_KEY`): cria um calendário por profissional sob a SA, compartilha best-effort com o e-mail dele. Upgrade opcional = **OAuth por-usuário** (`google_credentials`), que tem prioridade quando existe. Resolução em `app/services/calendar_provider.py`. Ver spec `2026-06-21-google-auth-dual-mode-design.md`.
```

- [ ] **Step 7: Full suite + lint**

Run: `uv run pytest -q && git diff --name-only | xargs uv run ruff check`
Expected: all green; slice files lint-clean.

- [ ] **Step 8: Commit**

```bash
git add app/api/agent_routes.py tests/unit/test_agent_route_calendar_wiring.py tests/integration/test_agent_message_endpoint.py env.example CLAUDE.md
git commit -m "feat(auth): wire dual-mode calendar provider into the agent route"
```

---

## Manual end-to-end (after Task 5)

For the human, once a Google Cloud **service account** JSON exists:
```bash
# .env: GOOGLE_CLIENT_EMAIL + GOOGLE_PRIVATE_KEY (from the SA key JSON)
make run
make chat MSG="agenda a Maria amanhã às 10h"   # creates a calendar under the SA + event, zero consent
```
The professional gets the calendar shared to their email (if it's a Google account). To switch a professional to their own calendar later: `uv run python scripts/google_auth.py <user_uuid>` (OAuth), after which their requests use `primary`.

---

## Self-Review notes

- **Spec coverage:** SA credentials (Task 1) ✓; create/share calendar (Task 2) ✓; ensure_calendar upsert of real id (Task 3) ✓; resolver OAuth-priority + SA-default + best-effort share + None fallback (Task 4) ✓; route wiring + user load + docs (Task 5) ✓.
- **No network in tests:** every Google call is behind an injected `build_resource` or a MagicMock resource; credential builders are monkeypatched.
- **Type consistency:** `build_calendar_access` returns `CalendarAccess | None`; route uses `access.service if access else None`. `GoogleCalendarService(resource, tz, calendar_id=…)` signature matches the agenda slice.
- **Conscious limitations** (documented in spec §7): mode switch does not migrate existing events; reads still via Postgres mirror.
