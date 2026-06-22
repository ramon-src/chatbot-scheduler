# WhatsApp Ingestion Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three follow-ups the final whole-branch review of the WhatsApp ingestion slice deferred: crash-window dropped agent runs (FU1), ambiguous normalized-phone matching (FU2), and the audit payload's column type (FU3).

**Architecture:** FU1 adds an `agent_run_at` marker on `inbound_message`; `dispatch_agent_run` becomes idempotent (skips an already-run record, marks the record when done) and the webhook opportunistically re-dispatches stale orphaned professional rows on each inbound request. FU2 materializes a `users.phone_normalized` column (kept in sync by a SQLAlchemy `@validates` hook on `User.phone`, backfilled by migration) with a unique index, and rewrites `resolve_sender` to match on it — making mis-routing impossible by construction. FU3 alters `inbound_message.raw` from `JSON` to `JSONB`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 (Column-style models), Alembic (schema `simplificapsi`), Pydantic AI, pytest (asyncio_mode=auto), ruff, uv.

## Global Constraints

- Code, identifiers, and enums in English; user-facing copy may be Portuguese.
- DB schema is always `simplificapsi` (models set `__table_args__` schema; migrations pass `schema="simplificapsi"`).
- Migrations chain linearly: 0007 → 0006, 0008 → 0007, 0009 → 0008; single head after.
- No hardcoded credentials.
- The agent never sees the provider (`InboundMessage.provider` stays ingestion-layer only).
- Idempotency: a redelivered/duplicate inbound is never processed twice; the opportunistic re-dispatch must never cause a double agent run (the `agent_run_at` guard enforces this).
- Best-effort webhook unchanged: after auth passes, both POST routes return 200; the sweep must never make a webhook raise.
- tz-aware timestamps throughout.

---

## File Structure

| File | Change |
|---|---|
| `app/models/inbound_message.py` | `raw` → JSONB (FU3); add `agent_run_at` column (FU1) |
| `app/models/user.py` | add `phone_normalized` column + unique index + `@validates("phone")` (FU2) |
| `app/services/ingestion_service.py` | idempotent `dispatch_agent_run(inbound, user_id, record_id)`; `find_orphan_professional_messages`; `build_inbound_from_record` (FU1) |
| `app/api/webhook_routes.py` | pass `record_id`; opportunistic orphan sweep (FU1) |
| `app/services/identity_service.py` | `resolve_sender` matches on `phone_normalized` (FU2) |
| `migrations/versions/0007_inbound_raw_jsonb.py` | FU3 |
| `migrations/versions/0008_inbound_agent_run_at.py` | FU1 |
| `migrations/versions/0009_users_phone_normalized.py` | FU2 |

---

### Task 1: FU3 — `inbound_message.raw` → JSONB

**Files:**
- Modify: `app/models/inbound_message.py`
- Create: `migrations/versions/0007_inbound_raw_jsonb.py`
- Test: `tests/unit/test_inbound_message_model.py` (extend)

**Interfaces:**
- Produces: `InboundMessageRecord.raw` typed as `postgresql.JSONB`.

- [ ] **Step 1: Write the failing test** (append to the existing test file)

```python
def test_raw_column_is_jsonb():
    from sqlalchemy.dialects.postgresql import JSONB
    col = InboundMessageRecord.__table__.columns["raw"]
    assert isinstance(col.type, JSONB)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_inbound_message_model.py::test_raw_column_is_jsonb -v`
Expected: FAIL (current type is `JSON`, not `JSONB`)

- [ ] **Step 3: Implement** — in `app/models/inbound_message.py`, change the import and the column.

Replace the `JSON` import: remove `JSON` from the `sqlalchemy` import list and add `JSONB` to the `sqlalchemy.dialects.postgresql` import:

```python
from sqlalchemy.dialects.postgresql import JSONB, UUID
```

Change the column:

```python
    raw = Column(JSONB, nullable=True)
```

Create the migration:

```python
# migrations/versions/0007_inbound_raw_jsonb.py
"""alter inbound_message.raw from JSON to JSONB

JSONB lets us index/query the audit payload later; JSON was write-only.

Revision ID: 0007_inbound_raw_jsonb
Revises: 0006_inbound_message
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_inbound_raw_jsonb"
down_revision = "0006_inbound_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "inbound_message",
        "raw",
        type_=postgresql.JSONB(),
        postgresql_using="raw::jsonb",
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.alter_column(
        "inbound_message",
        "raw",
        type_=sa.JSON(),
        postgresql_using="raw::json",
        schema="simplificapsi",
    )
```

- [ ] **Step 4: Run test + migration**

Run: `uv run pytest tests/unit/test_inbound_message_model.py -v`
Expected: PASS (incl. the existing model tests)

Run: `uv run alembic upgrade head`
Expected: `0006_inbound_message -> 0007_inbound_raw_jsonb` applies cleanly.

- [ ] **Step 5: Commit**

```bash
git add app/models/inbound_message.py migrations/versions/0007_inbound_raw_jsonb.py tests/unit/test_inbound_message_model.py
git commit -m "feat(ingestion): store inbound_message.raw as JSONB"
```

---

### Task 2: FU1 (part A) — `agent_run_at` marker + idempotent dispatch

**Files:**
- Modify: `app/models/inbound_message.py`
- Create: `migrations/versions/0008_inbound_agent_run_at.py`
- Modify: `app/services/ingestion_service.py`
- Modify: `app/api/webhook_routes.py`
- Modify: `tests/integration/test_ingestion_service.py`

**Interfaces:**
- Consumes: `InboundMessageRecord` (Task 1), `process_professional_message`.
- Produces:
  - `InboundMessageRecord.agent_run_at` (nullable tz DateTime).
  - `async dispatch_agent_run(inbound: InboundMessage, user_id: UUID, record_id: UUID) -> None` — NEW third parameter; idempotency guard: if the record is missing or already has `agent_run_at`, return without running; after a run, set `agent_run_at` and commit.
  - The webhook passes `result.record_id` when scheduling.

- [ ] **Step 1: Write the failing tests** (append to `tests/integration/test_ingestion_service.py`)

```python
async def test_dispatch_marks_agent_run_at(db_user_phone, monkeypatch):
    from datetime import datetime
    from app.models.inbound_message import InboundMessageRecord
    monkeypatch.setattr(agent_runner, "build_calendar_access", lambda db, user, settings: None, raising=False)

    def _noop(messages, info):
        return ModelResponse(parts=[TextPart("noop")])

    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("ok")])

    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop)):
        from app.agents.simplifica_agent import build_simplifica_agent
        agent = build_simplifica_agent()
    monkeypatch.setattr(ingestion_service, "build_simplifica_agent", lambda: agent)

    db = SessionLocal()
    try:
        res = IngestionService(db).handle(_make("MID-MARK-1", PRO_PHONE))
        assert res.status == "professional"
        record_id = res.record_id
    finally:
        db.close()

    inbound = _make("MID-MARK-1", PRO_PHONE)
    with agent.override(model=FunctionModel(scripted)):
        await dispatch_agent_run(inbound, DEV_USER_ID, record_id)

    db = SessionLocal()
    try:
        rec = db.get(InboundMessageRecord, record_id)
        assert rec.agent_run_at is not None
    finally:
        _purge_inbound(db, "MID-MARK-1")
        db.close()


async def test_dispatch_is_skipped_when_already_run(db_user_phone, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.core.config import settings as _settings
    from app.models.inbound_message import InboundMessageRecord

    ran = {"called": False}

    async def boom(*a, **k):
        ran["called"] = True
        raise AssertionError("agent must not run for an already-marked record")

    monkeypatch.setattr(ingestion_service, "process_professional_message", boom)

    db = SessionLocal()
    try:
        res = IngestionService(db).handle(_make("MID-SKIP-1", PRO_PHONE))
        rec = db.get(InboundMessageRecord, res.record_id)
        rec.agent_run_at = datetime.now(ZoneInfo(_settings.TIMEZONE))
        db.commit()
        record_id = res.record_id
    finally:
        db.close()

    await dispatch_agent_run(_make("MID-SKIP-1", PRO_PHONE), DEV_USER_ID, record_id)
    assert ran["called"] is False

    db = SessionLocal()
    try:
        _purge_inbound(db, "MID-SKIP-1")
    finally:
        db.close()
```

Also update the EXISTING `test_dispatch_agent_run_persists_a_turn` to pass the record id: change the call `await dispatch_agent_run(inbound, DEV_USER_ID)` to first create the record via `IngestionService(db).handle(inbound)` to obtain a `record_id`, then `await dispatch_agent_run(inbound, DEV_USER_ID, record_id)`. (The message id in that test is `MID-RUN-1`; reuse it for the handle call so the persisted record matches.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_ingestion_service.py -v`
Expected: FAIL — `dispatch_agent_run` takes 2 args, not 3; `agent_run_at` attribute does not exist.

- [ ] **Step 3: Implement**

In `app/models/inbound_message.py`, add the column after `received_at`:

```python
    agent_run_at = Column(DateTime(timezone=True), nullable=True)
```

Create the migration:

```python
# migrations/versions/0008_inbound_agent_run_at.py
"""add inbound_message.agent_run_at

Marks when the professional agent run for a message finished. NULL = not yet
run; the webhook opportunistically re-dispatches stale NULL rows (crash
recovery) without double-running (the marker is the idempotency guard).

Revision ID: 0008_inbound_agent_run_at
Revises: 0007_inbound_raw_jsonb
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_inbound_agent_run_at"
down_revision = "0007_inbound_raw_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_message",
        sa.Column("agent_run_at", sa.DateTime(timezone=True), nullable=True),
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_column("inbound_message", "agent_run_at", schema="simplificapsi")
```

In `app/services/ingestion_service.py`, add imports at the top (with the others):

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
```

Rewrite `dispatch_agent_run`:

```python
async def dispatch_agent_run(inbound: InboundMessage, user_id: UUID, record_id: UUID) -> None:
    """Run the professional agent for an already-recorded message, exactly once.

    Opens its own DB session (it runs after the webhook response, on a
    BackgroundTask). Idempotent: if the record is gone or already marked
    `agent_run_at`, it returns without running — this is what makes the
    opportunistic re-dispatch safe against double runs. Best-effort otherwise.
    """
    db = SessionLocal()
    try:
        record = db.get(InboundMessageRecord, record_id)
        if record is None or record.agent_run_at is not None:
            return
        user = db.get(User, user_id)
        if user is None:
            return
        agent = build_simplifica_agent()
        await process_professional_message(db, agent, user, inbound.text, inbound.sender_phone)
        record.agent_run_at = datetime.now(ZoneInfo(settings.TIMEZONE))
        db.commit()
    except Exception:  # noqa: BLE001 - background work must never raise
        logger.warning("agent run for inbound message failed", exc_info=True)
    finally:
        db.close()
```

In `app/api/webhook_routes.py`, update `_ingest_and_maybe_schedule` to pass the record id:

```python
def _ingest_and_maybe_schedule(db: Session, inbound: InboundMessage, background: BackgroundTasks) -> None:
    result = IngestionService(db).handle(inbound)
    if result.status == "professional" and result.user_id is not None:
        background.add_task(dispatch_agent_run, inbound, result.user_id, result.record_id)
```

- [ ] **Step 4: Run tests + migration**

Run: `uv run pytest tests/integration/test_ingestion_service.py tests/integration/test_webhook_routes.py -v`
Expected: PASS (new marker tests + updated dispatch test + webhook tests still green).

Run: `uv run alembic upgrade head`
Expected: `0007_inbound_raw_jsonb -> 0008_inbound_agent_run_at` applies cleanly.

- [ ] **Step 5: Commit**

```bash
git add app/models/inbound_message.py migrations/versions/0008_inbound_agent_run_at.py app/services/ingestion_service.py app/api/webhook_routes.py tests/integration/test_ingestion_service.py
git commit -m "feat(ingestion): mark agent_run_at; make dispatch idempotent"
```

---

### Task 3: FU1 (part B) — opportunistic orphan re-dispatch on the webhook

**Files:**
- Modify: `app/services/ingestion_service.py`
- Modify: `app/api/webhook_routes.py`
- Test: `tests/integration/test_orphan_resweep.py`

**Interfaces:**
- Consumes: `InboundMessageRecord`, `InboundMessage`, `dispatch_agent_run` (Task 2).
- Produces:
  - `find_orphan_professional_messages(db, older_than_minutes: int = 2, limit: int = 10) -> list[InboundMessageRecord]` — professional rows with `agent_run_at IS NULL` and `received_at < now - older_than_minutes`, oldest first, capped at `limit`.
  - `build_inbound_from_record(record: InboundMessageRecord) -> InboundMessage`.
  - The webhook's `_ingest_and_maybe_schedule` schedules a `dispatch_agent_run` for each orphan after handling the current message.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_orphan_resweep.py
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.inbound_message import InboundMessageRecord

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


def _evo_payload(message_id, remote_jid, text="oi"):
    return {
        "event": "messages.upsert",
        "instance": "psi",
        "data": {
            "key": {"remoteJid": remote_jid, "fromMe": False, "id": message_id},
            "message": {"conversation": text},
            "messageTimestamp": 1718900000,
            "pushName": "Fulano",
        },
    }


def _seed_orphan(message_id, *, minutes_old, agent_run_at=None, user_id=DEV_USER_ID,
                 classification="professional"):
    db = SessionLocal()
    try:
        rec = InboundMessageRecord(
            provider="evolution", provider_message_id=message_id,
            sender_phone="5551000000000", recipient_phone=None, text="oi",
            classification=classification, user_id=user_id, raw={"k": "v"},
            agent_run_at=agent_run_at,
        )
        db.add(rec)
        db.flush()
        rec.received_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
        db.commit()
        return rec.id
    finally:
        db.close()


def _purge(*ids):
    db = SessionLocal()
    try:
        db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id.in_(ids)
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_old_unrun_professional_orphan_is_redispatched(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    orphan_id = _seed_orphan("ORPH-OLD", minutes_old=5)
    scheduled = []

    async def fake_dispatch(inbound, user_id, record_id):
        scheduled.append((record_id, user_id, inbound.text))

    try:
        with patch("app.api.webhook_routes.dispatch_agent_run", side_effect=fake_dispatch):
            client = TestClient(app)
            # A fresh LEAD message (unknown number) — current message won't dispatch,
            # isolating the orphan sweep.
            r = client.post("/webhooks/evolution",
                            json=_evo_payload("SWEEP-TRIGGER", "5551911110000@s.whatsapp.net"))
            assert r.status_code == 200
        assert any(rid == orphan_id for rid, _, _ in scheduled), scheduled
    finally:
        _purge("ORPH-OLD", "SWEEP-TRIGGER")


def test_recent_orphan_is_not_redispatched(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    orphan_id = _seed_orphan("ORPH-RECENT", minutes_old=0)
    scheduled = []

    async def fake_dispatch(inbound, user_id, record_id):
        scheduled.append(record_id)

    try:
        with patch("app.api.webhook_routes.dispatch_agent_run", side_effect=fake_dispatch):
            client = TestClient(app)
            r = client.post("/webhooks/evolution",
                            json=_evo_payload("SWEEP-TRIGGER-2", "5551911110000@s.whatsapp.net"))
            assert r.status_code == 200
        assert orphan_id not in scheduled
    finally:
        _purge("ORPH-RECENT", "SWEEP-TRIGGER-2")


def test_already_run_orphan_is_not_redispatched(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    orphan_id = _seed_orphan("ORPH-DONE", minutes_old=5, agent_run_at=run_at)
    scheduled = []

    async def fake_dispatch(inbound, user_id, record_id):
        scheduled.append(record_id)

    try:
        with patch("app.api.webhook_routes.dispatch_agent_run", side_effect=fake_dispatch):
            client = TestClient(app)
            r = client.post("/webhooks/evolution",
                            json=_evo_payload("SWEEP-TRIGGER-3", "5551911110000@s.whatsapp.net"))
            assert r.status_code == 200
        assert orphan_id not in scheduled
    finally:
        _purge("ORPH-DONE", "SWEEP-TRIGGER-3")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_orphan_resweep.py -v`
Expected: FAIL — `find_orphan_professional_messages` does not exist / no sweep wired, so the orphan is never scheduled.

- [ ] **Step 3: Implement**

In `app/services/ingestion_service.py`, add `timedelta` to the datetime import (`from datetime import datetime, timedelta, timezone`) and append these functions:

```python
def find_orphan_professional_messages(
    db: Session, older_than_minutes: int = 2, limit: int = 10
) -> list[InboundMessageRecord]:
    """Professional rows whose agent run never completed (crash recovery).

    `older_than_minutes` keeps freshly-inserted rows — whose normal dispatch is
    still in flight — out of the sweep. Capped at `limit` to bound per-request work.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=older_than_minutes)
    return (
        db.query(InboundMessageRecord)
        .filter(
            InboundMessageRecord.classification == "professional",
            InboundMessageRecord.agent_run_at.is_(None),
            InboundMessageRecord.user_id.isnot(None),
            InboundMessageRecord.received_at < cutoff,
        )
        .order_by(InboundMessageRecord.received_at.asc())
        .limit(limit)
        .all()
    )


def build_inbound_from_record(record: InboundMessageRecord) -> InboundMessage:
    """Reconstruct the provider-agnostic InboundMessage from a stored row."""
    return InboundMessage(
        provider=record.provider,
        sender_phone=record.sender_phone,
        text=record.text,
        provider_message_id=record.provider_message_id,
        timestamp=record.received_at,
        recipient_phone=record.recipient_phone,
        raw=record.raw or {},
    )
```

In `app/api/webhook_routes.py`, import the new helpers and add the sweep. Update the import line:

```python
from app.services.ingestion_service import (
    IngestionService,
    build_inbound_from_record,
    dispatch_agent_run,
    find_orphan_professional_messages,
)
```

Rewrite `_ingest_and_maybe_schedule`:

```python
def _ingest_and_maybe_schedule(db: Session, inbound: InboundMessage, background: BackgroundTasks) -> None:
    result = IngestionService(db).handle(inbound)
    if result.status == "professional" and result.user_id is not None:
        background.add_task(dispatch_agent_run, inbound, result.user_id, result.record_id)
    # Opportunistic crash recovery: re-dispatch professional runs that never
    # completed. dispatch_agent_run's agent_run_at guard makes this double-safe.
    for orphan in find_orphan_professional_messages(db):
        background.add_task(
            dispatch_agent_run, build_inbound_from_record(orphan), orphan.user_id, orphan.id
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_orphan_resweep.py tests/integration/test_webhook_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/ingestion_service.py app/api/webhook_routes.py tests/integration/test_orphan_resweep.py
git commit -m "feat(ingestion): opportunistically re-dispatch orphaned professional runs"
```

---

### Task 4: FU2 — normalized-phone uniqueness at registration

**Files:**
- Modify: `app/models/user.py`
- Create: `migrations/versions/0009_users_phone_normalized.py`
- Modify: `app/services/identity_service.py`
- Test: `tests/integration/test_user_phone_normalized.py`

**Interfaces:**
- Produces:
  - `User.phone_normalized` (String(20), nullable, unique index `uq_users_phone_normalized`), derived from `User.phone` by a `@validates("phone")` hook.
  - `resolve_sender` matches on `User.phone_normalized` (exact equality), returning the single active match or None.

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_user_phone_normalized.py
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.user import User
from app.services.identity_service import resolve_sender


def _new_user(phone):
    return User(id=uuid4(), email=f"u-{uuid4().hex[:8]}@example.com", name="Pro", phone=phone)


def test_validates_sets_phone_normalized_on_assignment():
    u = _new_user("+55 (51) 99999-8888")
    assert u.phone_normalized == "5551999998888"


def test_blank_phone_yields_null_normalized():
    u = _new_user(None)
    assert u.phone_normalized is None


def test_two_users_same_normalized_phone_violate_unique():
    db = SessionLocal()
    a = _new_user("+5551999998888")
    b = _new_user("51 99999-8888")  # normalizes to the same 5551999998888
    db.add(a)
    db.commit()
    try:
        db.add(b)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.query(User).filter(User.id.in_([a.id, b.id])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_resolve_sender_matches_on_normalized_column():
    db = SessionLocal()
    u = _new_user("+55 (51) 98888-7777")
    db.add(u)
    db.commit()
    try:
        found = resolve_sender(db, "5551988887777@s.whatsapp.net")
        assert found is not None and found.id == u.id
    finally:
        db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
        db.commit()
        db.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_user_phone_normalized.py -v`
Expected: FAIL — `phone_normalized` attribute does not exist.

- [ ] **Step 3: Implement**

In `app/models/user.py`, add the `Index` and `validates` imports, the column, the unique index in `__table_args__`, and the validator. Concretely:

Imports:
```python
from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.orm import relationship, validates

from app.channels.phone import normalize_phone
```

Change `__table_args__` from the dict to a tuple carrying the unique index:
```python
    __table_args__ = (
        Index("uq_users_phone_normalized", "phone_normalized", unique=True),
        {"schema": "simplificapsi"},
    )
```

Add the column next to `phone`:
```python
    phone_normalized = Column(String(20), nullable=True)
```

Add the validator inside the class (e.g., just before `__repr__`):
```python
    @validates("phone")
    def _derive_phone_normalized(self, key, value):
        """Keep phone_normalized in sync with phone on every write (the
        registration-time enforcement point for the uniqueness constraint)."""
        self.phone_normalized = normalize_phone(value) or None
        return value
```

Create the migration (adds the column, backfills from existing `phone`, then adds the unique index):

```python
# migrations/versions/0009_users_phone_normalized.py
"""add users.phone_normalized with a unique index

Materializes the normalized phone so a sender number resolves to at most one
professional. Backfills existing rows, then enforces uniqueness.

Revision ID: 0009_users_phone_normalized
Revises: 0008_inbound_agent_run_at
"""
import sqlalchemy as sa
from alembic import op

from app.channels.phone import normalize_phone

revision = "0009_users_phone_normalized"
down_revision = "0008_inbound_agent_run_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone_normalized", sa.String(length=20), nullable=True),
        schema="simplificapsi",
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, phone FROM simplificapsi.users WHERE phone IS NOT NULL")
    ).fetchall()
    for row_id, phone in rows:
        norm = normalize_phone(phone)
        if norm:
            conn.execute(
                sa.text("UPDATE simplificapsi.users SET phone_normalized = :n WHERE id = :i"),
                {"n": norm, "i": row_id},
            )
    op.create_index(
        "uq_users_phone_normalized", "users", ["phone_normalized"], unique=True,
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_index("uq_users_phone_normalized", table_name="users", schema="simplificapsi")
    op.drop_column("users", "phone_normalized", schema="simplificapsi")
```

Rewrite `resolve_sender` in `app/services/identity_service.py` (the unique index guarantees at most one active match, so the Python scan is gone):

```python
def resolve_sender(db: Session, phone: str) -> User | None:
    target = normalize_phone(phone)
    if not target:
        return None
    return (
        db.query(User)
        .filter(User.is_active == True, User.phone_normalized == target)  # noqa: E712
        .first()
    )
```

- [ ] **Step 4: Run tests + migration**

Run: `uv run alembic upgrade head`
Expected: `0008_inbound_agent_run_at -> 0009_users_phone_normalized` applies cleanly. (If it fails on the unique index, the existing data already has two users with the same normalized phone — a real data problem to surface, not a plan bug.)

Run: `uv run pytest tests/integration/test_user_phone_normalized.py tests/integration/test_identity_service.py -v`
Expected: PASS (new tests + the existing identity tests stay green).

- [ ] **Step 5: Commit**

```bash
git add app/models/user.py migrations/versions/0009_users_phone_normalized.py app/services/identity_service.py tests/integration/test_user_phone_normalized.py
git commit -m "feat(identity): unique normalized phone; resolve_sender matches on it"
```

---

### Task 5: Full-suite + lint + migration verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole suite (excluding live)**

Run: `uv run pytest -m "not live" -q`
Expected: all pass.

- [ ] **Step 2: Lint**

Run: `uv run ruff check app tests migrations`
Expected: clean on the files this plan touched (pre-existing violations elsewhere are out of scope).

- [ ] **Step 3: Confirm migrations are linear**

Run: `uv run alembic heads`
Expected: single head `0009_users_phone_normalized`.

No commit (verification only).

---

## Self-Review

**Spec coverage:**
- FU1 crash-window dropped run → Tasks 2 (marker + idempotent dispatch) + 3 (opportunistic sweep). ✓
- FU2 ambiguous normalized phone → Task 4 (unique column + validator + resolve_sender rewrite). ✓
- FU3 raw JSON→JSONB → Task 1. ✓

**Placeholder scan:** no TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `dispatch_agent_run(inbound, user_id, record_id)` defined in Task 2, called with 3 args by the webhook in Tasks 2 and 3, and by the orphan sweep in Task 3. `find_orphan_professional_messages` / `build_inbound_from_record` defined and consumed in Task 3. `User.phone_normalized` defined in Task 4 and queried by `resolve_sender` in the same task. Migration chain 0007→0008→0009 over 0006. ✓

**Double-run safety:** `dispatch_agent_run` claims the row atomically via `UPDATE inbound_message SET agent_run_at = now() WHERE id = :id AND agent_run_at IS NULL`. Under READ COMMITTED exactly one concurrent caller wins this claim (the UPDATE returns 1); all others see 0 rows updated and return immediately without running the agent. This eliminates the check-then-act race of the previous read-then-check pattern. Trade-off: the row is marked *before* the agent run completes, so a crash mid-run leaves it claimed and will not be re-swept — a strictly smaller hazard than the double-run it replaces. The `older_than_minutes` cutoff keeps freshly-inserted rows (whose normal dispatch is still in flight) out of the orphan sweep. ✓
