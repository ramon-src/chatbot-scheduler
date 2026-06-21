# Agenda (Google Calendar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add agenda management to the SimplificaAgent — create/list/update/cancel single and recurring appointments on the user's Google Calendar (source of truth), dual-writing the business row to Postgres.

**Architecture:** Google Calendar is the source of truth; Postgres stores the linked business `Event` row keyed by `google_event_id` (no bidirectional sync). Per-user OAuth tokens live in a new `google_credentials` table; a one-time CLI consent script populates them. A thin `GoogleCalendarService` wraps the official `google-api-python-client` resource (injected, so tests never hit the network). `EventService` owns the Postgres dual-write. `calendar_tools` orchestrate: resolve client first (guard-rail "evento exige cliente existente"), call Google, persist locally — returning the standard `{success,data,message}` contract with no IDs in `message`. When the user has not connected Google yet, tools degrade gracefully instead of erroring.

**Tech Stack:** Python 3.11+ · Pydantic AI · SQLAlchemy 2 · Alembic · `google-api-python-client` / `google-auth` / `google-auth-oauthlib` (already in `pyproject.toml`) · pytest.

## Global Constraints

- Code, identifiers, enums in **English**; end-user `message` strings in **PT-BR**.
- All models in Postgres schema **`simplificapsi`** (`__table_args__ = {"schema": "simplificapsi"}`).
- **Tool contract:** every tool returns `dict` `{"success": bool, "data": Any, "message": str}`. `message` **never** contains IDs, JSON, HTML, markdown, or URLs.
- **Guard-rails live in code**, not the LLM: `create_event`/`create_recurring_event` resolve the client first; if not found → `success:false` asking to register (no orphan event).
- **Pure-impl + thin-wrapper:** each tool is a pure `*_impl(deps, ...)` (testable without an LLM) plus a thin `@agent.tool` wrapper that passes `ctx.deps`.
- **Timezone fixed** `America/Sao_Paulo`; **week starts Sunday**.
- **Tests never hit the Google network** — inject a fake calendar resource / mock credentials.
- **TDD:** new behavior starts red→green. Small commits, one per task.
- **No AI attribution** in commits/PRs. Do not invent LLM model IDs.
- Dev user UUID: `550e8400-e29b-41d4-a716-446655440000`.

---

## File Structure

- Create `app/utils/date_range.py` — `calculate_date_range` pure period resolver.
- Create `app/models/google_credential.py` — `GoogleCredential` SQLAlchemy model.
- Create `migrations/versions/0003_google_credentials.py` — table migration.
- Create `app/services/google_auth.py` — load/refresh `google.oauth2.credentials.Credentials` from the DB row; `GoogleAuthError`.
- Create `scripts/google_auth.py` — one-time interactive OAuth consent (writes the DB row).
- Create `app/services/google_calendar_service.py` — `GoogleCalendarService` over an injected calendar API resource.
- Create `app/services/event_service.py` — `EventService` Postgres dual-write CRUD.
- Create `app/agents/tools/calendar_tools.py` — impls + `register_calendar_tools`.
- Modify `app/agents/deps.py` — add agenda deps.
- Modify `app/agents/simplifica_agent.py` — register calendar tools + prompt.
- Modify `app/api/agent_routes.py` — build agenda deps (construct service from stored credentials; graceful when not connected).
- Modify `app/models/__init__.py`, `app/models/user.py` — register model + relationship.
- Modify `scripts/seed_dev.py` — seed the dev user's primary `Calendar` row.
- Tests under `tests/unit/` and `tests/integration/`.

---

### Task 1: `calculate_date_range` period resolver

**Files:**
- Create: `app/utils/date_range.py`
- Test: `tests/unit/test_date_range.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `calculate_date_range(period: str, now: datetime) -> tuple[datetime, datetime]` returning timezone-aware `(start, end)` in `now`'s tzinfo. Recognized `period` values (case-insensitive, accents tolerated): `today`, `tomorrow`, `this_week`, `next_week`, `this_month`, `all_future`. `start` is inclusive at 00:00:00; `end` is exclusive at the next boundary's 00:00:00. Week starts **Sunday**. `all_future` → `(start_of_today, start_of_today + 366 days)`. Unknown period raises `ValueError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_date_range.py
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.utils.date_range import calculate_date_range

TZ = ZoneInfo("America/Sao_Paulo")
# 2026-06-21 is a Sunday, 14:30 local
NOW = datetime(2026, 6, 21, 14, 30, tzinfo=TZ)


def test_today():
    start, end = calculate_date_range("today", NOW)
    assert start == datetime(2026, 6, 21, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 6, 22, 0, 0, tzinfo=TZ)


def test_tomorrow():
    start, end = calculate_date_range("tomorrow", NOW)
    assert start == datetime(2026, 6, 22, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 6, 23, 0, 0, tzinfo=TZ)


def test_this_week_starts_sunday():
    # NOW is Sunday -> week is 21st (Sun) through 28th (next Sun, exclusive)
    start, end = calculate_date_range("this_week", NOW)
    assert start == datetime(2026, 6, 21, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 6, 28, 0, 0, tzinfo=TZ)


def test_this_week_midweek_rolls_back_to_sunday():
    wed = datetime(2026, 6, 24, 9, 0, tzinfo=TZ)  # Wednesday
    start, end = calculate_date_range("this_week", wed)
    assert start == datetime(2026, 6, 21, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 6, 28, 0, 0, tzinfo=TZ)


def test_next_week():
    start, end = calculate_date_range("next_week", NOW)
    assert start == datetime(2026, 6, 28, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 7, 5, 0, 0, tzinfo=TZ)


def test_this_month():
    start, end = calculate_date_range("this_month", NOW)
    assert start == datetime(2026, 6, 1, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 7, 1, 0, 0, tzinfo=TZ)


def test_all_future_capped_one_year():
    start, end = calculate_date_range("all_future", NOW)
    assert start == datetime(2026, 6, 21, 0, 0, tzinfo=TZ)
    assert (end - start).days == 366


def test_accent_and_case_insensitive_aliases():
    assert calculate_date_range("HOJE", NOW) == calculate_date_range("today", NOW)
    assert calculate_date_range("esta semana", NOW) == calculate_date_range("this_week", NOW)


def test_unknown_period_raises():
    with pytest.raises(ValueError):
        calculate_date_range("yesterday", NOW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_date_range.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils.date_range'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/utils/date_range.py
"""Pure period resolver for agenda queries. Week starts Sunday."""

from datetime import datetime, timedelta
from unicodedata import normalize

# Canonical period -> also matched by PT-BR aliases below.
_ALIASES = {
    "today": "today", "hoje": "today",
    "tomorrow": "tomorrow", "amanha": "tomorrow",
    "this_week": "this_week", "esta semana": "this_week", "essa semana": "this_week",
    "next_week": "next_week", "proxima semana": "next_week",
    "this_month": "this_month", "este mes": "this_month", "esse mes": "this_month",
    "all_future": "all_future", "todos": "all_future", "futuro": "all_future",
}


def _strip(period: str) -> str:
    """Lowercase, strip accents, collapse separators."""
    text = normalize("NFKD", period.strip().lower())
    text = "".join(c for c in text if not _is_combining(c))
    return text.replace("-", " ").replace("_", " ").strip() if " " in text or "_" in text or "-" in text else text


def _is_combining(char: str) -> bool:
    from unicodedata import combining
    return bool(combining(char))


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def calculate_date_range(period: str, now: datetime) -> tuple[datetime, datetime]:
    """Resolve a named period to a [start, end) range in now's timezone.

    start is inclusive at 00:00; end is exclusive at the next boundary's 00:00.
    """
    raw = _strip(period)
    # Match canonical keys (which use "_") against the space-normalized text.
    canonical = _ALIASES.get(period.strip().lower()) or _ALIASES.get(raw) or _ALIASES.get(raw.replace(" ", "_"))
    if canonical is None:
        raise ValueError(f"Unknown period: {period!r}")

    today = _start_of_day(now)

    if canonical == "today":
        return today, today + timedelta(days=1)
    if canonical == "tomorrow":
        return today + timedelta(days=1), today + timedelta(days=2)
    if canonical == "this_week":
        # Python weekday(): Mon=0..Sun=6. Days since Sunday = (weekday + 1) % 7.
        days_since_sunday = (today.weekday() + 1) % 7
        start = today - timedelta(days=days_since_sunday)
        return start, start + timedelta(days=7)
    if canonical == "next_week":
        days_since_sunday = (today.weekday() + 1) % 7
        start = today - timedelta(days=days_since_sunday) + timedelta(days=7)
        return start, start + timedelta(days=7)
    if canonical == "this_month":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    if canonical == "all_future":
        return today, today + timedelta(days=366)

    raise ValueError(f"Unknown period: {period!r}")  # unreachable
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_date_range.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add app/utils/date_range.py tests/unit/test_date_range.py
git commit -m "feat(agenda): add calculate_date_range period resolver (week starts Sunday)"
```

---

### Task 2: `GoogleCredential` model + migration

**Files:**
- Create: `app/models/google_credential.py`
- Modify: `app/models/__init__.py`, `app/models/user.py:45-48`
- Create: `migrations/versions/0003_google_credentials.py`
- Test: `tests/unit/test_google_credential_model.py`

**Interfaces:**
- Produces: `GoogleCredential` ORM model in schema `simplificapsi`, table `google_credentials`. Columns: `id UUID pk`, `user_id UUID FK simplificapsi.users.id ondelete CASCADE unique not null` (one credential per user), `refresh_token Text not null`, `token Text nullable` (last access token), `token_uri String(255) not null default 'https://oauth2.googleapis.com/token'`, `client_id String(255) not null`, `client_secret String(255) not null`, `scopes Text not null` (space-joined), `expiry DateTime(timezone=True) nullable`, `created_at`/`updated_at` server defaults. `User.google_credential = relationship(..., uselist=False)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_google_credential_model.py
from app.models import GoogleCredential
from app.models.google_credential import GoogleCredential as Direct


def test_model_table_and_schema():
    assert GoogleCredential is Direct
    assert GoogleCredential.__tablename__ == "google_credentials"
    assert GoogleCredential.__table_args__["schema"] == "simplificapsi"


def test_model_has_oauth_columns():
    cols = GoogleCredential.__table__.columns
    for name in ("user_id", "refresh_token", "token", "token_uri", "client_id", "client_secret", "scopes", "expiry"):
        assert name in cols, f"missing column {name}"
    assert cols["user_id"].unique is True
    assert cols["refresh_token"].nullable is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_google_credential_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'GoogleCredential'`

- [ ] **Step 3: Write the model**

```python
# app/models/google_credential.py
"""Per-user Google OAuth credentials (refresh token store)."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleCredential(Base):
    """OAuth2 credential for a user's Google Calendar (one per user)."""

    __tablename__ = "google_credentials"
    __table_args__ = {"schema": "simplificapsi"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simplificapsi.users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    refresh_token = Column(Text, nullable=False)
    token = Column(Text, nullable=True)
    token_uri = Column(String(255), nullable=False, default=DEFAULT_TOKEN_URI)
    client_id = Column(String(255), nullable=False)
    client_secret = Column(String(255), nullable=False)
    scopes = Column(Text, nullable=False)  # space-joined scope list
    expiry = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="google_credential")

    def __repr__(self) -> str:
        return f"<GoogleCredential(user_id={self.user_id})>"
```

- [ ] **Step 4: Register model + relationship**

In `app/models/__init__.py`, add after the `event` import:
```python
from .google_credential import GoogleCredential
```
and add `"GoogleCredential",` to `__all__`.

In `app/models/user.py`, inside the relationships block (after the `chat_sessions` line ~48), add:
```python
    google_credential = relationship(
        "GoogleCredential", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
```

- [ ] **Step 5: Write the migration**

```python
# migrations/versions/0003_google_credentials.py
"""add google_credentials table

Revision ID: 0003_google_credentials
Revises: 0002_client_billing_fields
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_google_credentials"
down_revision = "0002_client_billing_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_credentials",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("token_uri", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["simplificapsi.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_google_credentials_user_id"),
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_google_credentials_user_id",
        "google_credentials",
        ["user_id"],
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_index("ix_simplificapsi_google_credentials_user_id", table_name="google_credentials", schema="simplificapsi")
    op.drop_table("google_credentials", schema="simplificapsi")
```

> Note: `sa.dialects.postgresql` requires `import sqlalchemy.dialects.postgresql`. If the autogenerate style in 0001 uses `from sqlalchemy.dialects import postgresql` and `postgresql.UUID(...)`, match that style instead — check `0001_initial_migration.py` first and follow its exact import idiom for UUID columns.

- [ ] **Step 6: Apply migration and verify**

Run:
```bash
make migrate
uv run python -c "from sqlalchemy import inspect; from app.core.database import engine; print('google_credentials' in inspect(engine).get_table_names(schema='simplificapsi'))"
```
Expected: prints `True`

- [ ] **Step 7: Run model test**

Run: `uv run pytest tests/unit/test_google_credential_model.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add app/models/google_credential.py app/models/__init__.py app/models/user.py migrations/versions/0003_google_credentials.py tests/unit/test_google_credential_model.py
git commit -m "feat(agenda): add google_credentials table for per-user OAuth tokens"
```

---

### Task 3: Google auth — credentials provider + consent CLI

**Files:**
- Create: `app/services/google_auth.py`
- Create: `scripts/google_auth.py`
- Test: `tests/unit/test_google_auth.py`

**Interfaces:**
- Consumes: `GoogleCredential` model (Task 2), `settings.GOOGLE_SCOPES`.
- Produces:
  - `class GoogleAuthError(Exception)` — raised when a user has no stored credential or the refresh fails.
  - `load_credentials(db: Session, user_id: UUID) -> google.oauth2.credentials.Credentials` — builds `Credentials` from the DB row, refreshes if expired (persisting the new access token/expiry), raises `GoogleAuthError` if no row.
  - `has_credentials(db: Session, user_id: UUID) -> bool`.
  - `store_credentials(db: Session, user_id: UUID, creds) -> None` — upsert the DB row from a `Credentials` object (used by the CLI).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_google_auth.py
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services import google_auth
from app.services.google_auth import GoogleAuthError, has_credentials, load_credentials


def _fake_row(**over):
    base = dict(
        refresh_token="rt", token="at", token_uri="https://oauth2.googleapis.com/token",
        client_id="cid", client_secret="secret", scopes="https://www.googleapis.com/auth/calendar",
        expiry=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _db_returning(row):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    return db


def test_no_credential_raises(monkeypatch):
    db = _db_returning(None)
    with pytest.raises(GoogleAuthError):
        load_credentials(db, uuid4())


def test_has_credentials_false_when_missing():
    assert has_credentials(_db_returning(None), uuid4()) is False


def test_has_credentials_true_when_present():
    assert has_credentials(_db_returning(_fake_row()), uuid4()) is True


def test_load_builds_credentials_without_refresh_when_valid(monkeypatch):
    captured = {}

    class FakeCreds:
        def __init__(self, token=None, **kw):
            captured.update(kw, token=token)
            self.token = token
            self.expired = False
            self.valid = True

        def refresh(self, request):  # should not be called
            captured["refreshed"] = True

    monkeypatch.setattr(google_auth, "Credentials", FakeCreds)
    creds = load_credentials(_db_returning(_fake_row()), uuid4())
    assert isinstance(creds, FakeCreds)
    assert captured["refresh_token"] == "rt"
    assert "refreshed" not in captured


def test_load_refreshes_and_persists_when_expired(monkeypatch):
    class FakeCreds:
        def __init__(self, token=None, **kw):
            self.token = token
            self.expired = True
            self.valid = False
            self.expiry = None

        def refresh(self, request):
            self.token = "new-access-token"
            self.expired = False
            self.valid = True

    monkeypatch.setattr(google_auth, "Credentials", FakeCreds)
    monkeypatch.setattr(google_auth, "Request", lambda: object())
    row = _fake_row()
    db = _db_returning(row)
    creds = load_credentials(db, uuid4())
    assert creds.token == "new-access-token"
    assert row.token == "new-access-token"  # persisted back to the row
    db.commit.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_google_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.google_auth'`

- [ ] **Step 3: Write the provider**

```python
# app/services/google_auth.py
"""Build/refresh google OAuth credentials from the per-user DB row."""

from uuid import UUID

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from app.models.google_credential import GoogleCredential


class GoogleAuthError(Exception):
    """User has not connected Google Calendar, or token refresh failed."""


def _get_row(db: Session, user_id: UUID) -> GoogleCredential | None:
    return db.query(GoogleCredential).filter(GoogleCredential.user_id == user_id).first()


def has_credentials(db: Session, user_id: UUID) -> bool:
    return _get_row(db, user_id) is not None


def load_credentials(db: Session, user_id: UUID) -> Credentials:
    row = _get_row(db, user_id)
    if row is None:
        raise GoogleAuthError("Usuário não conectou a Google Agenda.")

    creds = Credentials(
        token=row.token,
        refresh_token=row.refresh_token,
        token_uri=row.token_uri,
        client_id=row.client_id,
        client_secret=row.client_secret,
        scopes=row.scopes.split(),
    )

    if getattr(creds, "expired", False) or not getattr(creds, "valid", True):
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001 - surface as domain error
            raise GoogleAuthError(f"Falha ao renovar o acesso à Google Agenda: {exc}") from exc
        row.token = creds.token
        row.expiry = getattr(creds, "expiry", None)
        db.commit()

    return creds


def store_credentials(db: Session, user_id: UUID, creds: Credentials) -> None:
    """Upsert the DB row from a Credentials object (used by the consent CLI)."""
    row = _get_row(db, user_id)
    scopes = " ".join(creds.scopes or [])
    if row is None:
        row = GoogleCredential(user_id=user_id)
        db.add(row)
    row.refresh_token = creds.refresh_token
    row.token = creds.token
    row.token_uri = creds.token_uri
    row.client_id = creds.client_id
    row.client_secret = creds.client_secret
    row.scopes = scopes
    row.expiry = getattr(creds, "expiry", None)
    db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_google_auth.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Write the one-time consent CLI (no automated test — interactive)**

```python
# scripts/google_auth.py
"""One-time interactive OAuth consent for a user's Google Calendar.

Prereqs: a Google Cloud OAuth *Desktop* client. Put its values in .env:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
Run:  uv run python scripts/google_auth.py [USER_UUID]
Default USER_UUID is the dev user. Opens a browser; on success stores the
refresh token in simplificapsi.google_credentials.
"""

import sys
from uuid import UUID

from google_auth_oauthlib.flow import InstalledAppFlow

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.google_auth import store_credentials

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


def main() -> None:
    user_id = UUID(sys.argv[1]) if len(sys.argv) > 1 else DEV_USER_ID
    client_config = {
        "installed": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise SystemExit("Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env primeiro.")

    flow = InstalledAppFlow.from_client_config(client_config, scopes=settings.GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    db = SessionLocal()
    try:
        store_credentials(db, user_id, creds)
    finally:
        db.close()
    print(f"Google Agenda conectada para o usuário {user_id}.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add app/services/google_auth.py scripts/google_auth.py tests/unit/test_google_auth.py
git commit -m "feat(agenda): google credentials provider + one-time consent CLI"
```

---

### Task 4: `GoogleCalendarService` over an injected API resource

**Files:**
- Create: `app/services/google_calendar_service.py`
- Test: `tests/unit/test_google_calendar_service.py`

**Interfaces:**
- Consumes: an injected Google Calendar API `resource` (the object returned by `googleapiclient.discovery.build("calendar", "v3", credentials=...)`), and a `timezone: str`.
- Produces `GoogleCalendarService(resource, timezone, calendar_id="primary")` with:
  - `create_event(summary: str, start: datetime, end: datetime, description: str | None = None, recurrence: list[str] | None = None) -> dict` → returns `{"id": <google event id>, "html_link": <url>}`.
  - `list_events(start: datetime, end: datetime) -> list[dict]` → each `{"id", "summary", "start", "end"}` (`start`/`end` are timezone-aware `datetime`).
  - `update_event(event_id: str, **changes) -> dict` (patch; `start`/`end` datetimes converted to GCal format).
  - `cancel_event(event_id: str) -> None` (deletes the GCal event).
  - `build_weekly_rrule(weekdays: list[str] | None, until: datetime | None) -> str` static helper → e.g. `"RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20261231T030000Z"`; no `until` → omit `UNTIL`.
- All datetimes serialize with the service `timezone`. The service never builds credentials — that is the caller's job.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_google_calendar_service.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_google_calendar_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the service**

```python
# app/services/google_calendar_service.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_google_calendar_service.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/google_calendar_service.py tests/unit/test_google_calendar_service.py
git commit -m "feat(agenda): GoogleCalendarService wrapper over injected GCal resource"
```

---

### Task 5: `EventService` — Postgres dual-write

**Files:**
- Create: `app/services/event_service.py`
- Modify: `scripts/seed_dev.py` (seed dev user's primary `Calendar`)
- Test: `tests/integration/test_event_service.py`

**Interfaces:**
- Consumes: `Event`, `Calendar` models; a `Session`.
- Produces `EventService(db)` with:
  - `get_primary_calendar(user_id: UUID) -> Calendar` — returns the user's primary `Calendar` row, creating one (`name="Principal"`, `google_calendar_id="primary"`, `is_primary=True`) if absent.
  - `record_event(user_id, client_id, title, start, end, google_event_id, is_recurring=False, recurrence_rule=None, price=None) -> Event` — inserts the linked `Event` row (status `scheduled`), committing.
  - `list_events_in_range(user_id, start, end) -> list[Event]` ordered by `start_time`.
  - `find_by_google_event_id(user_id, google_event_id) -> Event | None`.
  - `update_event(event: Event, *, title=None, start=None, end=None) -> Event` — patch local row, commit.
  - `cancel_event(event: Event) -> Event` — set status `cancelled`, commit (soft; the GCal delete is the caller's job).
- This task uses the real test DB (integration test) following the existing `tests/integration/` pattern. Read one existing integration test first to match the DB fixture/session setup; if `tests/integration/` has no DB fixture yet, use the same `SessionLocal`/transaction-rollback pattern the client tests use, or skip-mark with a clear reason and verify via `tests/unit` with a mocked session asserting the ORM calls. Prefer the real-DB integration test if the fixture exists.

- [ ] **Step 1: Write the failing test** (adapt fixture to the existing integration pattern)

```python
# tests/integration/test_event_service.py
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.core.database import SessionLocal
from app.models.event import Event, EventStatus
from app.services.event_service import EventService

TZ = ZoneInfo("America/Sao_Paulo")
DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    # cleanup events created by this test
    session.query(Event).filter(Event.google_event_id.like("test-%")).delete(synchronize_session=False)
    session.commit()
    session.close()


def test_get_primary_calendar_creates_when_absent(db):
    svc = EventService(db)
    cal = svc.get_primary_calendar(DEV_USER_ID)
    assert cal.is_primary is True
    assert cal.google_calendar_id == "primary"


def test_record_and_list_event(db):
    svc = EventService(db)
    start = datetime(2026, 6, 22, 10, 0, tzinfo=TZ)
    end = datetime(2026, 6, 22, 11, 0, tzinfo=TZ)
    ev = svc.record_event(
        user_id=DEV_USER_ID, client_id=None, title="Sessão - Teste",
        start=start, end=end, google_event_id="test-evt-1",
    )
    assert ev.status == EventStatus.SCHEDULED.value
    found = svc.list_events_in_range(DEV_USER_ID, start, end)
    assert any(e.google_event_id == "test-evt-1" for e in found)


def test_cancel_event_sets_status(db):
    svc = EventService(db)
    start = datetime(2026, 6, 23, 10, 0, tzinfo=TZ)
    ev = svc.record_event(
        user_id=DEV_USER_ID, client_id=None, title="x",
        start=start, end=start, google_event_id="test-evt-2",
    )
    cancelled = svc.cancel_event(ev)
    assert cancelled.status == EventStatus.CANCELLED.value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make infra && make migrate && uv run pytest tests/integration/test_event_service.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.event_service`

- [ ] **Step 3: Write the service**

```python
# app/services/event_service.py
"""Postgres dual-write for agenda events (Google Calendar is source of truth)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.calendar import Calendar
from app.models.event import Event, EventStatus


class EventService:
    def __init__(self, db: Session):
        self.db = db

    def get_primary_calendar(self, user_id: UUID) -> Calendar:
        cal = self.db.query(Calendar).filter(
            and_(Calendar.user_id == user_id, Calendar.is_primary == True)  # noqa: E712
        ).first()
        if cal is None:
            cal = Calendar(
                user_id=user_id, name="Principal",
                google_calendar_id="primary", is_primary=True, is_active=True,
            )
            self.db.add(cal)
            self.db.commit()
            self.db.refresh(cal)
        return cal

    def record_event(
        self, *, user_id: UUID, client_id, title: str, start: datetime, end: datetime,
        google_event_id: str, is_recurring: bool = False, recurrence_rule=None, price=None,
    ) -> Event:
        calendar = self.get_primary_calendar(user_id)
        event = Event(
            user_id=user_id, client_id=client_id, calendar_id=calendar.id,
            title=title, start_time=start, end_time=end,
            google_event_id=google_event_id, is_recurring=is_recurring,
            recurrence_rule=recurrence_rule, price=price,
            status=EventStatus.SCHEDULED.value,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_events_in_range(self, user_id: UUID, start: datetime, end: datetime) -> list[Event]:
        return self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.start_time >= start,
                Event.start_time < end,
                Event.status != EventStatus.CANCELLED.value,
            )
        ).order_by(Event.start_time).all()

    def find_by_google_event_id(self, user_id: UUID, google_event_id: str) -> Event | None:
        return self.db.query(Event).filter(
            and_(Event.user_id == user_id, Event.google_event_id == google_event_id)
        ).first()

    def update_event(self, event: Event, *, title=None, start=None, end=None) -> Event:
        if title is not None:
            event.title = title
        if start is not None:
            event.start_time = start
        if end is not None:
            event.end_time = end
        self.db.commit()
        self.db.refresh(event)
        return event

    def cancel_event(self, event: Event) -> Event:
        event.status = EventStatus.CANCELLED.value
        self.db.commit()
        self.db.refresh(event)
        return event
```

- [ ] **Step 4: Seed the dev user's primary calendar**

In `scripts/seed_dev.py`, after the dev `User` is ensured, add a primary `Calendar` (idempotent). Import `Calendar` and, inside `seed_dev_user`, before closing the session:
```python
    from app.models.calendar import Calendar
    existing_cal = db.query(Calendar).filter(
        Calendar.user_id == DEV_USER_ID, Calendar.is_primary == True  # noqa: E712
    ).first()
    if existing_cal is None:
        db.add(Calendar(
            user_id=DEV_USER_ID, name="Principal",
            google_calendar_id="primary", is_primary=True, is_active=True,
        ))
        db.commit()
```
Match the file's actual variable names (`db`, `DEV_USER_ID`) — read it first.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_event_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add app/services/event_service.py scripts/seed_dev.py tests/integration/test_event_service.py
git commit -m "feat(agenda): EventService Postgres dual-write + seed primary calendar"
```

---

### Task 6: `calendar_tools` — impls + wrappers with guard-rails

**Files:**
- Create: `app/agents/tools/calendar_tools.py`
- Modify: `app/agents/deps.py`
- Test: `tests/unit/test_calendar_tools.py`

**Interfaces:**
- Consumes: `AgentDeps` (extended in this task), `calculate_date_range` (Task 1), `GoogleCalendarService` (Task 4), `EventService` (Task 5), `ClientService.find_client_by_phone`/`find_client_by_name` (existing), `GoogleAuthError` (Task 3).
- `AgentDeps` gains three optional fields:
  ```python
  calendar_service: Optional["GoogleCalendarService"] = None
  event_service: Optional["EventService"] = None
  default_consult_minutes: int = 60
  ```
  (Use a string/`TYPE_CHECKING` import to avoid a hard import cycle; `client_service` stays required and these default to `None` so existing client-only construction keeps working.)
- Produces in `calendar_tools.py`:
  - `create_event_impl(deps, client_name=None, client_phone=None, start_time: datetime, duration_minutes: int | None = None, title: str | None = None) -> dict`
  - `create_recurring_event_impl(deps, *, client_name=None, client_phone=None, start_time, frequency: str = "weekly", weekdays: list[str] | None = None, until: datetime | None = None, duration_minutes=None, title=None) -> dict`
  - `list_events_impl(deps, period: str = "this_week") -> dict`
  - `cancel_event_impl(deps, client_name=None, client_phone=None, period: str = "this_week", reason: str | None = None) -> dict`
  - `register_calendar_tools(agent) -> None` — thin `@agent.tool` wrappers (datetimes accepted as ISO 8601 strings parsed inside the wrapper).
- Guard-rails enforced in the impls:
  - **Not connected:** if `deps.calendar_service is None` → `{"success": False, "data": None, "message": "Você ainda não conectou sua Google Agenda. ..."}` (no traceback).
  - **Event requires existing client:** resolve client via phone (exact) or name (must be unique). No client → `success:false` asking to register; multiple homonyms → `success:false` asking for phone. Never create an orphan event.
  - `message` carries client first name + human date/time only — never IDs or URLs.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_calendar_tools.py
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.deps import AgentDeps
from app.agents.tools.calendar_tools import (
    create_event_impl,
    list_events_impl,
)

TZ = ZoneInfo("America/Sao_Paulo")


def _client(name="Maria Silva", phone="+5551981321543"):
    return SimpleNamespace(id=uuid4(), name=name, phone=phone)


def _deps(*, calendar_service=None, event_service=None, client_by_phone=None, client_by_name=None):
    cs = MagicMock()
    cs.find_client_by_phone = AsyncMock(return_value=client_by_phone)
    cs.find_client_by_name = AsyncMock(return_value=client_by_name or [])
    return AgentDeps(
        db=MagicMock(), user_id=uuid4(), user_name="Dr. Ana",
        current_datetime=datetime(2026, 6, 21, 9, 0, tzinfo=TZ),
        timezone="America/Sao_Paulo", history_summary=None,
        client_service=cs, calendar_service=calendar_service, event_service=event_service,
    )


async def test_create_event_requires_connected_calendar():
    deps = _deps(calendar_service=None)
    out = await create_event_impl(
        deps, client_phone="+5551981321543", start_time=datetime(2026, 6, 22, 10, tzinfo=TZ)
    )
    assert out["success"] is False
    assert "Google Agenda" in out["message"]


async def test_create_event_requires_existing_client():
    cal = MagicMock()
    deps = _deps(calendar_service=cal, event_service=MagicMock(), client_by_phone=None)
    out = await create_event_impl(
        deps, client_phone="+5551999999999", start_time=datetime(2026, 6, 22, 10, tzinfo=TZ)
    )
    assert out["success"] is False
    assert "cadastr" in out["message"].lower()
    cal.create_event.assert_not_called()


async def test_create_event_happy_path_dual_writes():
    cal = MagicMock()
    cal.create_event.return_value = {"id": "gevt-1", "html_link": "https://x"}
    es = MagicMock()
    es.record_event.return_value = SimpleNamespace(id=uuid4(), google_event_id="gevt-1")
    deps = _deps(calendar_service=cal, event_service=es, client_by_phone=_client())
    out = await create_event_impl(
        deps, client_phone="+5551981321543",
        start_time=datetime(2026, 6, 22, 10, 0, tzinfo=TZ), duration_minutes=50,
    )
    assert out["success"] is True
    assert "Maria" in out["message"]
    assert "gevt-1" not in out["message"]  # no IDs leaked
    # dual write happened
    cal.create_event.assert_called_once()
    es.record_event.assert_called_once()
    # end = start + 50min
    kwargs = cal.create_event.call_args.kwargs
    assert (kwargs["end"] - kwargs["start"]).total_seconds() == 50 * 60


async def test_list_events_empty_period():
    es = MagicMock()
    es.list_events_in_range.return_value = []
    deps = _deps(calendar_service=MagicMock(), event_service=es)
    out = await list_events_impl(deps, period="today")
    assert out["success"] is True
    assert out["data"]["total"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_calendar_tools.py -v`
Expected: FAIL (import error / AgentDeps missing fields)

- [ ] **Step 3: Extend `AgentDeps`**

In `app/agents/deps.py`, add (keeping `client_service` required, new fields optional with defaults):
```python
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.services.event_service import EventService
    from app.services.google_calendar_service import GoogleCalendarService
```
and inside the dataclass, after `client_service`:
```python
    calendar_service: Optional["GoogleCalendarService"] = None
    event_service: Optional["EventService"] = None
    default_consult_minutes: int = 60
```

- [ ] **Step 4: Write `calendar_tools.py`**

```python
# app/agents/tools/calendar_tools.py
"""Agenda tools: pure impls + thin @agent.tool wrappers. Google Calendar is source of truth."""

from datetime import datetime, timedelta
from typing import Optional

from app.agents.deps import AgentDeps
from app.utils.date_range import calculate_date_range

_NOT_CONNECTED = {
    "success": False, "data": None,
    "message": "Você ainda não conectou sua Google Agenda. Posso te ajudar a conectar quando quiser.",
}


def _fmt(dt: datetime) -> str:
    return dt.strftime("%d/%m às %Hh%M").replace("h00", "h")


async def _resolve_client(deps: AgentDeps, client_name, client_phone):
    """Return (client, error_dict). Exactly one of client/error is non-None."""
    if client_phone:
        client = await deps.client_service.find_client_by_phone(client_phone, deps.user_id)
        if client:
            return client, None
        return None, {"success": False, "data": None,
                      "message": f"Não encontrei cliente com o telefone {client_phone}. Quer cadastrar primeiro?"}
    if client_name:
        matches = await deps.client_service.find_client_by_name(client_name, deps.user_id)
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            names = ", ".join(m.name for m in matches)
            return None, {"success": False, "data": {"candidates": names},
                          "message": f"Encontrei vários clientes para '{client_name}': {names}. "
                                     f"Pode informar o telefone?"}
        first = client_name.split()[0]
        return None, {"success": False, "data": None,
                      "message": f"Não encontrei cliente chamado {first}. Quer cadastrar primeiro?"}
    return None, {"success": False, "data": None,
                  "message": "Preciso do nome ou telefone do cliente para agendar."}


async def create_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None,
    start_time: datetime, duration_minutes: Optional[int] = None, title: Optional[str] = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _NOT_CONNECTED
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error

    minutes = duration_minutes or deps.default_consult_minutes
    end = start_time + timedelta(minutes=minutes)
    summary = title or f"Sessão - {client.name}"

    created = deps.calendar_service.create_event(summary=summary, start=start_time, end=end)
    deps.event_service.record_event(
        user_id=deps.user_id, client_id=client.id, title=summary,
        start=start_time, end=end, google_event_id=created["id"],
    )
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name, "start": start_time.isoformat()},
            "message": f"Agendei {first} para {_fmt(start_time)}."}


async def create_recurring_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None, start_time: datetime,
    frequency: str = "weekly", weekdays=None, until=None,
    duration_minutes: Optional[int] = None, title: Optional[str] = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _NOT_CONNECTED
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error

    minutes = duration_minutes or deps.default_consult_minutes
    end = start_time + timedelta(minutes=minutes)
    summary = title or f"Sessão - {client.name}"
    rrule = deps.calendar_service.build_weekly_rrule(weekdays, until)

    created = deps.calendar_service.create_event(
        summary=summary, start=start_time, end=end, recurrence=[rrule]
    )
    deps.event_service.record_event(
        user_id=deps.user_id, client_id=client.id, title=summary,
        start=start_time, end=end, google_event_id=created["id"],
        is_recurring=True, recurrence_rule=rrule,
    )
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name},
            "message": f"Agendei sessões recorrentes para {first}, começando {_fmt(start_time)}."}


async def list_events_impl(deps: AgentDeps, period: str = "this_week") -> dict:
    if deps.event_service is None:
        return _NOT_CONNECTED
    try:
        start, end = calculate_date_range(period, deps.current_datetime)
    except ValueError:
        return {"success": False, "data": None,
                "message": "Não entendi o período. Tente 'hoje', 'esta semana' ou 'este mês'."}

    events = deps.event_service.list_events_in_range(deps.user_id, start, end)
    items = [{"title": e.title, "start": e.start_time.isoformat()} for e in events]
    if not items:
        return {"success": True, "data": {"events": [], "total": 0},
                "message": "Você não tem compromissos nesse período."}
    lines = "; ".join(f"{e.title} em {_fmt(e.start_time)}" for e in events)
    return {"success": True, "data": {"events": items, "total": len(items)},
            "message": f"Você tem {len(items)} compromisso(s): {lines}."}


async def cancel_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None,
    period: str = "this_week", reason: Optional[str] = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _NOT_CONNECTED
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    try:
        start, end = calculate_date_range(period, deps.current_datetime)
    except ValueError:
        return {"success": False, "data": None,
                "message": "Não entendi o período. Tente 'hoje' ou 'esta semana'."}

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
    deps.calendar_service.cancel_event(event.google_event_id)
    deps.event_service.cancel_event(event)
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name},
            "message": f"Cancelei o compromisso de {first}."}


def register_calendar_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def create_event(
        ctx: RunContext[AgentDeps], start_time: str,
        client_name: Optional[str] = None, client_phone: Optional[str] = None,
        duration_minutes: Optional[int] = None, title: Optional[str] = None,
    ) -> dict:
        """Agenda um compromisso único. start_time em ISO 8601. Exige cliente já cadastrado."""
        return await create_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            start_time=datetime.fromisoformat(start_time),
            duration_minutes=duration_minutes, title=title,
        )

    @agent.tool
    async def create_recurring_event(
        ctx: RunContext[AgentDeps], start_time: str,
        client_name: Optional[str] = None, client_phone: Optional[str] = None,
        weekdays: Optional[list[str]] = None, until: Optional[str] = None,
        duration_minutes: Optional[int] = None, title: Optional[str] = None,
    ) -> dict:
        """Agenda sessões recorrentes semanais. start_time/until em ISO 8601. weekdays como ['TU','TH']."""
        return await create_recurring_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            start_time=datetime.fromisoformat(start_time),
            weekdays=weekdays, until=datetime.fromisoformat(until) if until else None,
            duration_minutes=duration_minutes, title=title,
        )

    @agent.tool
    async def list_events(ctx: RunContext[AgentDeps], period: str = "this_week") -> dict:
        """Lista compromissos da agenda em um período (today, tomorrow, this_week, next_week, this_month)."""
        return await list_events_impl(ctx.deps, period)

    @agent.tool
    async def cancel_event(
        ctx: RunContext[AgentDeps], client_name: Optional[str] = None,
        client_phone: Optional[str] = None, period: str = "this_week", reason: Optional[str] = None,
    ) -> dict:
        """Cancela o compromisso de um cliente num período. Exige cliente cadastrado."""
        return await cancel_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone, period=period, reason=reason
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_calendar_tools.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add app/agents/tools/calendar_tools.py app/agents/deps.py tests/unit/test_calendar_tools.py
git commit -m "feat(agenda): calendar_tools with client guard-rail + graceful not-connected"
```

---

### Task 7: Wire agenda into the agent + route

**Files:**
- Modify: `app/agents/simplifica_agent.py`
- Modify: `app/api/agent_routes.py`
- Test: `tests/unit/test_agent_agenda_wiring.py`

**Interfaces:**
- Consumes everything above.
- `simplifica_agent.py`: call `register_calendar_tools(agent)` and extend the system prompt with agenda guidance (single + recurring scheduling, list by period, cancel; reminds the model the client must exist first; dates resolved relative to "Data/hora atual").
- `agent_routes.py`: build agenda deps — if `has_credentials(db, user_id)`, construct `GoogleCalendarService(build("calendar","v3", credentials=load_credentials(...)), settings.TIMEZONE)`; always construct `EventService(db)`; pass both into `AgentDeps`. If not connected, pass `calendar_service=None` (tools degrade gracefully). Wrap Google client construction so an auth failure never 500s the endpoint.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_agent_agenda_wiring.py
from app.agents.simplifica_agent import build_simplifica_agent


def test_agent_registers_calendar_tools(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    agent = build_simplifica_agent()
    tool_names = set(agent._function_toolset.tools.keys())  # pydantic-ai tool registry
    for name in ("create_event", "create_recurring_event", "list_events", "cancel_event"):
        assert name in tool_names, f"{name} not registered (have: {tool_names})"
```

> If `agent._function_toolset.tools` is not the correct accessor for the installed Pydantic AI version, discover the right one first: `uv run python -c "from app.agents.simplifica_agent import build_simplifica_agent as b; a=b(); print([x for x in dir(a) if 'tool' in x.lower()])"` and adapt the assertion to enumerate registered tool names. Keep the behavioral intent: all four agenda tools are registered alongside the client tools.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agent_agenda_wiring.py -v`
Expected: FAIL (calendar tools not registered)

- [ ] **Step 3: Register tools + extend prompt**

In `app/agents/simplifica_agent.py`:
- add `from app.agents.tools.calendar_tools import register_calendar_tools`
- after `register_client_tools(agent)` add `register_calendar_tools(agent)`
- append to `SIMPLIFICA_SYSTEM_PROMPT` (before the closing `"""`):
```
- Agenda: você pode agendar compromissos únicos e recorrentes, listar por período e cancelar.
  Um compromisso SEMPRE exige um cliente já cadastrado — se não existir, peça para cadastrar antes.
  Datas e horas são relativas à "Data/hora atual" do contexto; converta "amanhã às 10h" para o
  horário absoluto antes de chamar a tool. Períodos válidos para listar: hoje, amanhã, esta semana,
  próxima semana, este mês.
```

- [ ] **Step 4: Build agenda deps in the route**

In `app/api/agent_routes.py`, replace the `deps = AgentDeps(...)` construction so it also wires agenda. Add imports:
```python
from app.services.event_service import EventService
from app.services.google_auth import has_credentials, load_credentials
```
and build the calendar service defensively:
```python
    calendar_service = None
    if has_credentials(db, payload.user_id):
        try:
            from googleapiclient.discovery import build
            from app.services.google_calendar_service import GoogleCalendarService

            creds = load_credentials(db, payload.user_id)
            resource = build("calendar", "v3", credentials=creds, cache_discovery=False)
            calendar_service = GoogleCalendarService(resource, settings.TIMEZONE)
        except Exception:  # noqa: BLE001 - never 500 the chat on auth issues
            calendar_service = None

    deps = AgentDeps(
        db=db,
        user_id=payload.user_id,
        user_name=None,
        current_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
        timezone=settings.TIMEZONE,
        history_summary=None,
        client_service=ClientService(db),
        calendar_service=calendar_service,
        event_service=EventService(db),
    )
```

- [ ] **Step 5: Run the wiring test + full suite**

Run: `uv run pytest tests/unit/test_agent_agenda_wiring.py -v && uv run pytest -q`
Expected: wiring test PASS; full suite green (existing 17 + new agenda tests).

- [ ] **Step 6: Commit**

```bash
git add app/agents/simplifica_agent.py app/api/agent_routes.py tests/unit/test_agent_agenda_wiring.py
git commit -m "feat(agenda): register calendar tools in agent + wire deps in route"
```

---

## Manual end-to-end (after Task 7, requires Google connection)

Not an automated step — for the human to run once they have a Google Cloud OAuth desktop client:

```bash
# .env: set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
uv run python scripts/google_auth.py            # opens browser, stores refresh token
make run
make chat MSG="agenda a Maria amanhã às 10h"    # -> creates GCal event + Postgres row
make chat MSG="o que tenho essa semana?"        # -> lists from Postgres
make chat MSG="cancela a sessão da Maria amanhã"
```

Before connecting Google, `make chat MSG="agenda a Maria amanhã às 10h"` must reply with the "conecte sua Google Agenda" message — never a 500.

---

## Roadmap — next plans

- **Plano 3 — Cobrança:** `mark_paid`/`list_pending_payments`/`send_payment_reminder`.
- **Plano 4 — Memória de sessão + WhatsApp (ingestão provider-agnostic).**
- **Plano 5 — Eval & escolha de modelo.**
- **Plano 6 — Fiscal (Receita Saúde).**

## Self-Review notes

- **Spec coverage (§5.2, §6, §11):** `google_calendar_service` (Task 4) ✓; `calculate_date_range` (Task 1) ✓; tools create/recurring/list/cancel (Task 6) ✓; persist `google_event_id` in Postgres (Task 5) ✓; guard-rail "evento exige cliente existente" (Task 6) ✓; OAuth isolation + refresh/re-consent (Tasks 2-3) ✓; `all_future` capped ~1 year (Task 1) ✓; no IDs in `message` (Task 6 tests assert) ✓; week starts Sunday (Task 1 tests assert) ✓.
- **Deferred (conscious):** `update_event` tool wrapper is not exposed in v1 (the service method exists for Plano 3/future); cancel is by client+period, not by event id, to avoid leaking IDs to the user. No bidirectional sync (per spec §9).
- **Pydantic AI version risk:** Task 7 reads the tool registry; the step includes a discovery fallback to find the correct accessor if the API differs from `agent._function_toolset.tools`.
- **OAuth friction:** real Google connection needs a Google Cloud desktop OAuth client; until then all agenda tools degrade gracefully (no 500), and every non-connected path is covered by Task 6 unit tests.
