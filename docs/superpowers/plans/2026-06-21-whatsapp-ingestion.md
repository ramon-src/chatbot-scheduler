# WhatsApp Ingestion (provider-agnostic) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Receive inbound WhatsApp messages from multiple providers (Evolution API default, Meta Cloud scaffold), normalize to one internal format, and route by sender identity — professional numbers run the existing agent, unknown numbers are parked as leads.

**Architecture:** Ports & adapters. Each provider has an inbound adapter that translates its raw webhook payload into a single `InboundMessage` DTO. An `IngestionService` resolves sender identity (against `User.phone`), persists every message to an `inbound_message` table (idempotency + audit + lead queue), and routes: professionals reuse an extracted `process_professional_message` core; unknown numbers are parked. Webhook ack is synchronous for the cheap path (parse, idempotency, classify) and the slow agent run is deferred via FastAPI `BackgroundTasks`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 (Column-style models), Alembic (schema `simplificapsi`), Pydantic AI, pytest (asyncio_mode=auto), ruff, uv.

## Global Constraints

- Code, identifiers, and enums in English; user-facing copy may be Portuguese.
- Never hardcode credentials; all provider secrets come from `Settings` (env). New settings are `Optional` with safe defaults.
- The agent must never see the provider: `InboundMessage.provider` is used only by the ingestion layer, never passed into agent deps or prompts.
- Tool/response contract unchanged: agent replies are plain text; no IDs/URLs leak into user-facing copy.
- Timezone is `settings.TIMEZONE` (America/Sao_Paulo). All persisted timestamps are tz-aware.
- DB schema is always `simplificapsi` (models set `__table_args__ = {"schema": "simplificapsi"}`; migrations pass `schema="simplificapsi"`).
- Idempotency: a redelivered webhook (same `provider` + `provider_message_id`) must never be processed twice.
- Best-effort webhook: a downstream failure (agent, persistence) must still return HTTP 200 so providers stop redelivering; failures are logged, not raised.
- **Outbound is out of scope.** The professional agent reply is persisted in chat history but NOT sent back over WhatsApp.
- **No client/lead-facing agent.** Unknown numbers are parked only.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/channels/__init__.py` | package marker |
| `app/channels/inbound.py` | `InboundMessage` dataclass + `InboundAdapter` Protocol |
| `app/channels/phone.py` | `normalize_phone()` for matching |
| `app/channels/evolution_adapter.py` | Evolution payload → `InboundMessage` (complete) |
| `app/channels/meta_adapter.py` | Meta Cloud payload → `InboundMessage` (scaffold) + `verify_meta_token` / `valid_meta_signature` |
| `app/models/inbound_message.py` | `InboundMessage` ORM table (idempotency + audit + lead queue) |
| `migrations/versions/0006_inbound_message.py` | creates `inbound_message` |
| `app/services/identity_service.py` | `resolve_sender(db, phone) -> User \| None` |
| `app/services/agent_runner.py` | extracted `process_professional_message(...)` reused by HTTP + webhook |
| `app/services/ingestion_service.py` | `IngestionService.handle(inbound) -> IngestionResult` + `dispatch_agent_run(...)` |
| `app/api/webhook_routes.py` | `GET/POST /webhooks/whatsapp` (Meta), `POST /webhooks/evolution` |
| `app/core/config.py` | new Evolution settings |
| `app/main.py` | register webhook router |

ORM class name note: to avoid confusion with the DTO `InboundMessage` in `app/channels/inbound.py`, the ORM class is named **`InboundMessageRecord`** (table `inbound_message`).

---

### Task 1: Inbound port — `InboundMessage` DTO + `InboundAdapter` Protocol

**Files:**
- Create: `app/channels/__init__.py`
- Create: `app/channels/inbound.py`
- Test: `tests/unit/test_inbound_port.py`

**Interfaces:**
- Produces:
  - `InboundMessage` frozen dataclass: `provider: str`, `sender_phone: str`, `text: str`, `provider_message_id: str`, `timestamp: datetime`, `recipient_phone: str | None`, `raw: dict`.
  - `InboundAdapter` Protocol: attribute `provider: str`; method `parse(self, payload: dict) -> InboundMessage | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_inbound_port.py
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from app.channels.inbound import InboundMessage


def test_inbound_message_is_frozen_and_holds_fields():
    msg = InboundMessage(
        provider="evolution",
        sender_phone="5551999998888",
        text="olá",
        provider_message_id="ABC123",
        timestamp=datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc),
        recipient_phone="5551888887777",
        raw={"k": "v"},
    )
    assert msg.provider == "evolution"
    assert msg.sender_phone == "5551999998888"
    assert msg.text == "olá"
    assert msg.provider_message_id == "ABC123"
    assert msg.recipient_phone == "5551888887777"
    assert msg.raw == {"k": "v"}
    with pytest.raises(FrozenInstanceError):
        msg.text = "mutado"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_inbound_port.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.channels'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/channels/__init__.py
```

```python
# app/channels/inbound.py
"""Provider-agnostic inbound message port.

Every WhatsApp provider has an adapter that translates its raw webhook payload
into a single `InboundMessage`. The agent never sees `provider` — only the
ingestion layer uses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class InboundMessage:
    provider: str
    sender_phone: str
    text: str
    provider_message_id: str
    timestamp: datetime
    recipient_phone: str | None
    raw: dict


@runtime_checkable
class InboundAdapter(Protocol):
    provider: str

    def parse(self, payload: dict) -> InboundMessage | None:
        """Translate a raw provider webhook payload into an InboundMessage.

        Returns None for non-message events (delivery/read statuses, presence,
        echoes of our own outbound messages, etc.).
        """
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_inbound_port.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/channels/__init__.py app/channels/inbound.py tests/unit/test_inbound_port.py
git commit -m "feat(channels): inbound message port (DTO + adapter protocol)"
```

---

### Task 2: Phone normalization

**Files:**
- Create: `app/channels/phone.py`
- Test: `tests/unit/test_phone_normalization.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `normalize_phone(raw: str | None) -> str` — returns a canonical digits-only Brazilian number (`55` + DDD + number), or `""` for empty/None input.

**Normalization rules:** strip anything after `@` (Evolution JIDs like `5551999998888@s.whatsapp.net`); remove all non-digit characters (drops `+`, spaces, parentheses, dashes); if the result has 10 or 11 digits (DDD + number, no country code), prepend `55`. Known limitation: the Brazilian mobile "9th digit" can make two representations of the same line differ; this is documented and left for a later hardening pass.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_phone_normalization.py
import pytest

from app.channels.phone import normalize_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("5551999998888@s.whatsapp.net", "5551999998888"),
        ("5551999998888@c.us", "5551999998888"),
        ("+55 (51) 99999-8888", "5551999998888"),
        ("5551999998888", "5551999998888"),
        ("51999998888", "5551999998888"),       # 11 digits -> prepend 55
        ("(51) 99999-8888", "5551999998888"),    # 11 digits after strip
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_phone_normalization.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.channels.phone'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/channels/phone.py
"""Phone normalization for matching inbound senders against User.phone.

Reduces any representation (Evolution JID, +55 formatting, bare DDD+number) to a
canonical digits-only Brazilian number: ``55`` + DDD + number. Known limitation:
the Brazilian mobile 9th digit can make two representations of the same line
differ; handled on the common case only.
"""

from __future__ import annotations

import re

_DIGITS = re.compile(r"\D")


def normalize_phone(raw: str | None) -> str:
    if not raw:
        return ""
    local = raw.split("@", 1)[0]
    digits = _DIGITS.sub("", local)
    if not digits:
        return ""
    # Bare DDD + number (10 or 11 digits) -> assume Brazil country code.
    if len(digits) in (10, 11):
        digits = "55" + digits
    return digits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_phone_normalization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/channels/phone.py tests/unit/test_phone_normalization.py
git commit -m "feat(channels): canonical phone normalization for sender matching"
```

---

### Task 3: Evolution inbound adapter

**Files:**
- Create: `app/channels/evolution_adapter.py`
- Test: `tests/unit/test_evolution_adapter.py`

**Interfaces:**
- Consumes: `InboundMessage` (Task 1), `normalize_phone` (Task 2).
- Produces: `EvolutionInboundAdapter` with `provider = "evolution"` and `parse(payload: dict) -> InboundMessage | None`.

**Payload shape:** Evolution emits `{"event": "messages.upsert", "instance": ..., "data": {"key": {"remoteJid": "...@s.whatsapp.net", "fromMe": false, "id": "..."}, "message": {"conversation": "..."} | {"extendedTextMessage": {"text": "..."}}, "messageTimestamp": 1718900000, "pushName": "..."}}`. Return `None` unless `event == "messages.upsert"`, `fromMe` is falsy, and a text body is present.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_evolution_adapter.py
from datetime import timezone

from app.channels.evolution_adapter import EvolutionInboundAdapter


def _payload(**over):
    base = {
        "event": "messages.upsert",
        "instance": "psi",
        "data": {
            "key": {"remoteJid": "5551999998888@s.whatsapp.net", "fromMe": False, "id": "EVT1"},
            "message": {"conversation": "quero marcar uma sessão"},
            "messageTimestamp": 1718900000,
            "pushName": "Fulano",
        },
    }
    base.update(over)
    return base


def test_parses_conversation_message():
    msg = EvolutionInboundAdapter().parse(_payload())
    assert msg is not None
    assert msg.provider == "evolution"
    assert msg.sender_phone == "5551999998888"
    assert msg.text == "quero marcar uma sessão"
    assert msg.provider_message_id == "EVT1"
    assert msg.timestamp.tzinfo == timezone.utc
    assert msg.raw["event"] == "messages.upsert"


def test_parses_extended_text_message():
    p = _payload()
    p["data"]["message"] = {"extendedTextMessage": {"text": "olá de novo"}}
    msg = EvolutionInboundAdapter().parse(p)
    assert msg is not None and msg.text == "olá de novo"


def test_ignores_from_me_echo():
    p = _payload()
    p["data"]["key"]["fromMe"] = True
    assert EvolutionInboundAdapter().parse(p) is None


def test_ignores_non_message_event():
    assert EvolutionInboundAdapter().parse({"event": "messages.update", "data": {}}) is None


def test_ignores_message_without_text():
    p = _payload()
    p["data"]["message"] = {"imageMessage": {"url": "x"}}
    assert EvolutionInboundAdapter().parse(p) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_evolution_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/channels/evolution_adapter.py
"""Evolution API inbound adapter: raw webhook payload -> InboundMessage."""

from __future__ import annotations

from datetime import datetime, timezone

from app.channels.inbound import InboundMessage
from app.channels.phone import normalize_phone


def _extract_text(message: dict) -> str | None:
    if not isinstance(message, dict):
        return None
    conversation = message.get("conversation")
    if isinstance(conversation, str) and conversation:
        return conversation
    extended = message.get("extendedTextMessage")
    if isinstance(extended, dict):
        text = extended.get("text")
        if isinstance(text, str) and text:
            return text
    return None


class EvolutionInboundAdapter:
    provider = "evolution"

    def parse(self, payload: dict) -> InboundMessage | None:
        if payload.get("event") != "messages.upsert":
            return None
        data = payload.get("data") or {}
        key = data.get("key") or {}
        if key.get("fromMe"):
            return None
        text = _extract_text(data.get("message") or {})
        if text is None:
            return None
        remote_jid = key.get("remoteJid") or ""
        message_id = key.get("id") or ""
        ts_raw = data.get("messageTimestamp")
        try:
            timestamp = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        except (TypeError, ValueError):
            timestamp = datetime.now(tz=timezone.utc)
        return InboundMessage(
            provider=self.provider,
            sender_phone=normalize_phone(remote_jid),
            text=text,
            provider_message_id=message_id,
            timestamp=timestamp,
            recipient_phone=None,
            raw=payload,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_evolution_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/channels/evolution_adapter.py tests/unit/test_evolution_adapter.py
git commit -m "feat(channels): Evolution inbound adapter"
```

---

### Task 4: Meta Cloud inbound adapter (scaffold) + verification helpers

**Files:**
- Create: `app/channels/meta_adapter.py`
- Test: `tests/unit/test_meta_adapter.py`

**Interfaces:**
- Consumes: `InboundMessage` (Task 1), `normalize_phone` (Task 2).
- Produces:
  - `MetaInboundAdapter` with `provider = "meta"` and `parse(payload: dict) -> InboundMessage | None`.
  - `verify_meta_handshake(mode: str | None, token: str | None, challenge: str | None, expected_token: str) -> str | None` — returns `challenge` when `mode == "subscribe"` and `token == expected_token`, else `None`.
  - `valid_meta_signature(raw_body: bytes, header: str | None, app_secret: str | None) -> bool` — HMAC-SHA256; returns `True` when `app_secret` is falsy (signature check disabled in dev) OR the header matches.

**Payload shape:** Meta emits `{"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"metadata": {"display_phone_number": "..."}, "messages": [{"from": "5551999998888", "id": "wamid.X", "timestamp": "1718900000", "type": "text", "text": {"body": "..."}}]}}]}]}`. Status-only payloads carry `value.statuses` and no `value.messages` → `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_meta_adapter.py
import hashlib
import hmac

from app.channels.meta_adapter import (
    MetaInboundAdapter,
    valid_meta_signature,
    verify_meta_handshake,
)


def _msg_payload():
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"display_phone_number": "5551888887777"},
                            "messages": [
                                {
                                    "from": "5551999998888",
                                    "id": "wamid.ABC",
                                    "timestamp": "1718900000",
                                    "type": "text",
                                    "text": {"body": "olá pelo meta"},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def test_parses_meta_text_message():
    msg = MetaInboundAdapter().parse(_msg_payload())
    assert msg is not None
    assert msg.provider == "meta"
    assert msg.sender_phone == "5551999998888"
    assert msg.text == "olá pelo meta"
    assert msg.provider_message_id == "wamid.ABC"
    assert msg.recipient_phone == "5551888887777"


def test_ignores_status_only_payload():
    payload = {"object": "whatsapp_business_account",
               "entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert MetaInboundAdapter().parse(payload) is None


def test_handshake_returns_challenge_on_valid_token():
    assert verify_meta_handshake("subscribe", "tok", "ch123", "tok") == "ch123"


def test_handshake_rejects_bad_token():
    assert verify_meta_handshake("subscribe", "wrong", "ch123", "tok") is None


def test_signature_disabled_when_no_secret():
    assert valid_meta_signature(b"{}", None, None) is True


def test_signature_matches():
    body = b'{"a":1}'
    secret = "shh"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert valid_meta_signature(body, f"sha256={digest}", secret) is True
    assert valid_meta_signature(body, "sha256=deadbeef", secret) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_meta_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/channels/meta_adapter.py
"""Meta Cloud API inbound adapter (scaffold) + webhook verification helpers.

Secondary provider behind the same port as Evolution. Implemented enough to
parse a text message and verify the webhook; not the default channel.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

from app.channels.inbound import InboundMessage
from app.channels.phone import normalize_phone


class MetaInboundAdapter:
    provider = "meta"

    def parse(self, payload: dict) -> InboundMessage | None:
        try:
            change = payload["entry"][0]["changes"][0]["value"]
        except (KeyError, IndexError, TypeError):
            return None
        messages = change.get("messages")
        if not messages:
            return None
        message = messages[0]
        if message.get("type") != "text":
            return None
        body = (message.get("text") or {}).get("body")
        if not body:
            return None
        ts_raw = message.get("timestamp")
        try:
            timestamp = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        except (TypeError, ValueError):
            timestamp = datetime.now(tz=timezone.utc)
        recipient = (change.get("metadata") or {}).get("display_phone_number")
        return InboundMessage(
            provider=self.provider,
            sender_phone=normalize_phone(message.get("from")),
            text=body,
            provider_message_id=message.get("id") or "",
            timestamp=timestamp,
            recipient_phone=normalize_phone(recipient) or None,
            raw=payload,
        )


def verify_meta_handshake(
    mode: str | None, token: str | None, challenge: str | None, expected_token: str
) -> str | None:
    if mode == "subscribe" and token and token == expected_token:
        return challenge
    return None


def valid_meta_signature(raw_body: bytes, header: str | None, app_secret: str | None) -> bool:
    if not app_secret:
        return True  # signature verification disabled (dev)
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_meta_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/channels/meta_adapter.py tests/unit/test_meta_adapter.py
git commit -m "feat(channels): Meta Cloud inbound adapter scaffold + webhook verification"
```

---

### Task 5: `inbound_message` model + migration 0006

**Files:**
- Create: `app/models/inbound_message.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/0006_inbound_message.py`
- Test: `tests/unit/test_inbound_message_model.py`

**Interfaces:**
- Produces: `InboundMessageRecord` ORM model, table `simplificapsi.inbound_message`, columns: `id` (UUID PK), `provider` (String), `provider_message_id` (String), `sender_phone` (String), `recipient_phone` (String null), `text` (Text), `classification` (String: `"professional"|"lead"`), `user_id` (UUID null, FK `simplificapsi.users.id`), `raw` (JSON), `received_at` (DateTime tz, server_default now). Unique constraint `uq_inbound_provider_msg` on `(provider, provider_message_id)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_inbound_message_model.py
from app.models.inbound_message import InboundMessageRecord


def test_table_and_columns():
    t = InboundMessageRecord.__table__
    assert t.schema == "simplificapsi"
    assert t.name == "inbound_message"
    cols = set(t.columns.keys())
    assert {
        "id", "provider", "provider_message_id", "sender_phone",
        "recipient_phone", "text", "classification", "user_id", "raw", "received_at",
    } <= cols
    uniques = [
        tuple(sorted(c.name for c in con.columns))
        for con in t.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("provider", "provider_message_id") in uniques


def test_exported_from_models_package():
    from app.models import InboundMessageRecord as Exported
    assert Exported is InboundMessageRecord
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_inbound_message_model.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/models/inbound_message.py
"""Inbound WhatsApp message record: idempotency + audit + lead queue."""

import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class InboundMessageRecord(Base):
    """One received WhatsApp message, regardless of provider.

    `classification` is "professional" when `sender_phone` matched a User, else
    "lead". Lead rows are the queue a future client-facing agent will consume.
    """

    __tablename__ = "inbound_message"
    __table_args__ = (
        UniqueConstraint("provider", "provider_message_id", name="uq_inbound_provider_msg"),
        {"schema": "simplificapsi"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, index=True)
    provider_message_id = Column(String(255), nullable=False)
    sender_phone = Column(String(20), nullable=False, index=True)
    recipient_phone = Column(String(20), nullable=True)
    text = Column(Text, nullable=False)
    classification = Column(String(20), nullable=False, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simplificapsi.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw = Column(JSON, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<InboundMessageRecord(provider={self.provider}, "
            f"msg_id={self.provider_message_id}, class={self.classification})>"
        )
```

Modify `app/models/__init__.py` — add import and `__all__` entry:

```python
from .inbound_message import InboundMessageRecord
```
and add `"InboundMessageRecord",` to `__all__`.

```python
# migrations/versions/0006_inbound_message.py
"""create inbound_message table

Stores every received WhatsApp message (any provider) for idempotency, audit,
and as the lead queue for unlinked numbers.

Revision ID: 0006_inbound_message
Revises: 0005_chat_session_summary
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_inbound_message"
down_revision = "0005_chat_session_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("sender_phone", sa.String(length=20), nullable=False),
        sa.Column("recipient_phone", sa.String(length=20), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["simplificapsi.users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("provider", "provider_message_id", name="uq_inbound_provider_msg"),
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_inbound_message_provider", "inbound_message", ["provider"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_inbound_message_sender_phone", "inbound_message", ["sender_phone"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_inbound_message_classification", "inbound_message", ["classification"],
        schema="simplificapsi",
    )
    op.create_index(
        "ix_simplificapsi_inbound_message_user_id", "inbound_message", ["user_id"],
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_table("inbound_message", schema="simplificapsi")
```

- [ ] **Step 4: Run test + apply migration**

Run: `uv run pytest tests/unit/test_inbound_message_model.py -v`
Expected: PASS

Run: `uv run alembic upgrade head`
Expected: migration `0006_inbound_message` applies cleanly (creates `simplificapsi.inbound_message`).

- [ ] **Step 5: Commit**

```bash
git add app/models/inbound_message.py app/models/__init__.py migrations/versions/0006_inbound_message.py tests/unit/test_inbound_message_model.py
git commit -m "feat(models): inbound_message table (idempotency + audit + lead queue)"
```

---

### Task 6: Identity service — `resolve_sender`

**Files:**
- Create: `app/services/identity_service.py`
- Test: `tests/integration/test_identity_service.py`

**Interfaces:**
- Consumes: `normalize_phone` (Task 2), `User` model (`User.phone`).
- Produces: `resolve_sender(db: Session, phone: str) -> User | None` — normalizes `phone` and every candidate `User.phone`, returns the matching active `User` or `None`. Empty/blank phone → `None`.

Note: `User.phone` may be stored in any format, so matching normalizes BOTH sides rather than relying on a normalized column.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_identity_service.py
from uuid import UUID, uuid4

import pytest

from app.core.database import SessionLocal
from app.models.user import User
from app.services.identity_service import resolve_sender

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def test_resolves_known_professional_by_phone(db):
    email = f"id-{uuid4().hex[:8]}@example.com"
    user = User(id=uuid4(), email=email, name="Profissional", phone="+55 (51) 99999-8888")
    db.add(user)
    db.commit()
    try:
        found = resolve_sender(db, "5551999998888@s.whatsapp.net")
        assert found is not None and found.id == user.id
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()


def test_unknown_number_returns_none(db):
    assert resolve_sender(db, "5551000000000") is None


def test_blank_phone_returns_none(db):
    assert resolve_sender(db, "") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_identity_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/identity_service.py
"""Resolve an inbound sender phone to a registered professional (User)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.channels.phone import normalize_phone
from app.models.user import User


def resolve_sender(db: Session, phone: str) -> User | None:
    target = normalize_phone(phone)
    if not target:
        return None
    candidates = (
        db.query(User)
        .filter(User.is_active == True, User.phone.isnot(None))  # noqa: E712
        .all()
    )
    for user in candidates:
        if normalize_phone(user.phone) == target:
            return user
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_identity_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/identity_service.py tests/integration/test_identity_service.py
git commit -m "feat(identity): resolve inbound sender to a registered professional"
```

---

### Task 7: Extract reusable agent core — `process_professional_message`

**Files:**
- Create: `app/services/agent_runner.py`
- Modify: `app/api/agent_routes.py`
- Test: `tests/integration/test_agent_runner.py`

**Interfaces:**
- Consumes: `ChatHistoryService`, `to_model_messages`, `summarize_conversation`, `build_calendar_access`, `AgentDeps`, `ClientService`, `EventService` (all already used by `agent_routes.py`).
- Produces: in `app/services/agent_runner.py`:
  - `RAW_HISTORY_LIMIT = 10`, `DEV_PHONE = "dev-cli"` (moved here; `agent_routes` imports them back).
  - `build_agent_deps(db, user, history_summary=None) -> AgentDeps`
  - `async process_professional_message(db, agent, user, text, phone) -> str` — runs the full memory flow (session → replay → run → persist turn best-effort → fold summary) and returns the agent's text output.

This is a **pure refactor**: behavior must not change. The existing memory tests (`tests/integration/test_agent_memory.py`) are the regression guard and must stay green. `agent_routes.py` keeps its `agent_message` endpoint and unknown-user one-shot path, but delegates the known-user branch to `process_professional_message`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_agent_runner.py
from unittest.mock import patch
from uuid import UUID

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.models.user import User
from app.services.agent_runner import process_professional_message
from app.services import agent_runner

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
TEST_PHONE = "+5500000000077"


def _cleanup():
    db = SessionLocal()
    try:
        rows = db.query(ChatSession).filter(ChatSession.phone_number == TEST_PHONE).all()
        for s in rows:
            db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete(
                synchronize_session=False
            )
        db.query(ChatSession).filter(ChatSession.phone_number == TEST_PHONE).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


async def test_process_persists_turn_and_returns_output(monkeypatch):
    _cleanup()
    monkeypatch.setattr(agent_runner, "build_calendar_access", lambda db, user, settings: None)

    def _noop(messages, info):
        return ModelResponse(parts=[TextPart("noop")])

    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop)):
        from app.agents.simplifica_agent import build_simplifica_agent
        agent = build_simplifica_agent()

    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("resposta do agente")])

    db = SessionLocal()
    try:
        user = db.get(User, DEV_USER_ID)
        with agent.override(model=FunctionModel(scripted)):
            out = await process_professional_message(db, agent, user, "oi", TEST_PHONE)
        assert out == "resposta do agente"
        session = db.query(ChatSession).filter(
            ChatSession.user_id == DEV_USER_ID, ChatSession.phone_number == TEST_PHONE
        ).one()
        msgs = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.asc()).all()
        assert [m.message_type for m in msgs] == ["user", "assistant"]
        assert msgs[1].content == "resposta do agente"
    finally:
        db.close()
        _cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_agent_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.agent_runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/agent_runner.py
"""Reusable professional-agent processing core.

Shared by the HTTP /agent/message route and the WhatsApp webhook ingestion so
both drive the exact same memory flow (replay -> run -> persist -> fold).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agents.deps import AgentDeps
from app.agents.history import to_model_messages
from app.agents.summarizer import summarize_conversation
from app.core.config import settings
from app.core.logging import get_logger
from app.services.calendar_provider import build_calendar_access
from app.services.chat_history_service import ChatHistoryService
from app.services.client_service import ClientService
from app.services.event_service import EventService

logger = get_logger(__name__)

# Most recent messages fed to the model verbatim; older ones live in the summary.
RAW_HISTORY_LIMIT = 10
# Fallback conversation channel for local/dev calls without a real WhatsApp number.
DEV_PHONE = "dev-cli"


def build_agent_deps(db: Session, user, history_summary: str | None = None) -> AgentDeps:
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
        history_summary=history_summary,
        client_service=ClientService(db),
        calendar_service=access.service if access else None,
        event_service=EventService(db),
    )


def _persist_turn(db, history, session, user_text, assistant_text) -> bool:
    try:
        history.append_turn(session, user_text, assistant_text)
        return True
    except Exception:  # noqa: BLE001 - never lose the answer after it is computed
        logger.warning("failed to persist conversation turn", exc_info=True)
        db.rollback()
        return False


async def _maybe_update_summary(history: ChatHistoryService, session) -> None:
    try:
        pending = history.unsummarized_overflow(session, keep_recent=RAW_HISTORY_LIMIT)
        if not pending:
            return
        new_summary = await summarize_conversation(session.summary, pending)
        history.fold_summary(session, new_summary, (session.summarized_count or 0) + len(pending))
    except Exception:  # noqa: BLE001 - summary is best-effort; never break the chat
        logger.warning("conversation summary update failed", exc_info=True)


async def process_professional_message(db: Session, agent, user, text: str, phone: str) -> str:
    """Run the full memory flow for a known professional and return the reply text."""
    history = ChatHistoryService(db)
    session = history.get_or_create_session(user.id, phone or DEV_PHONE)
    message_history = to_model_messages(history.recent_messages(session, RAW_HISTORY_LIMIT))

    deps = build_agent_deps(db, user, history_summary=session.summary)
    result = await agent.run(text, deps=deps, message_history=message_history)

    if _persist_turn(db, history, session, text, result.output):
        await _maybe_update_summary(history, session)
    return result.output
```

Rewrite `app/api/agent_routes.py` to delegate to the runner (behavior unchanged):

```python
"""HTTP entrypoint for the SimplificaAgent."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.simplifica_agent import build_simplifica_agent
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.agent_runner import (
    DEV_PHONE,
    build_agent_deps,
    process_professional_message,
)

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentMessageRequest(BaseModel):
    user_id: UUID
    message: str
    phone_number: str | None = None


class AgentMessageResponse(BaseModel):
    content: str


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest, db: Session = Depends(get_db)):
    agent = build_simplifica_agent()
    user = db.get(User, payload.user_id)

    # Unknown users get a one-shot answer (the chat_sessions FK needs a real user).
    if user is None:
        deps = build_agent_deps(
            db, User(id=payload.user_id, name="profissional", email=None), history_summary=None
        )
        result = await agent.run(payload.message, deps=deps)
        return AgentMessageResponse(content=result.output)

    reply = await process_professional_message(
        db, agent, user, payload.message, payload.phone_number or DEV_PHONE
    )
    return AgentMessageResponse(content=reply)
```

Note for the implementer: `tests/integration/test_agent_memory.py` patches `agent_routes.build_simplifica_agent`, `agent_routes.build_calendar_access`, and `agent_routes.summarize_conversation`. After this refactor, `build_calendar_access` and `summarize_conversation` live in `agent_runner`. Update those patch targets in `test_agent_memory.py` to `agent_runner.build_calendar_access` / `agent_runner.summarize_conversation` (and import `from app.services import agent_runner`). `build_simplifica_agent` is still imported/used in `agent_routes`, so that patch target stays. Keep every assertion identical — only the patch targets move.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_agent_runner.py tests/integration/test_agent_memory.py -v`
Expected: PASS (new runner test + all existing memory regression tests green)

- [ ] **Step 5: Commit**

```bash
git add app/services/agent_runner.py app/api/agent_routes.py tests/integration/test_agent_runner.py tests/integration/test_agent_memory.py
git commit -m "refactor(agent): extract reusable process_professional_message core"
```

---

### Task 8: Ingestion service — idempotency, classify, route

**Files:**
- Create: `app/services/ingestion_service.py`
- Test: `tests/integration/test_ingestion_service.py`

**Interfaces:**
- Consumes: `InboundMessage` (Task 1), `resolve_sender` (Task 6), `InboundMessageRecord` (Task 5), `process_professional_message` + `build_simplifica_agent` (Task 7).
- Produces:
  - `@dataclass IngestionResult`: `status: str` (`"duplicate"|"professional"|"lead"`), `user_id: UUID | None`, `record_id: UUID | None`.
  - `class IngestionService(db)`:
    - `handle(self, inbound: InboundMessage) -> IngestionResult` — synchronous & deterministic: dedupe on `(provider, provider_message_id)`; resolve sender; persist an `InboundMessageRecord` classified `professional` (with `user_id`) or `lead`; return the result. No LLM call here.
  - `async dispatch_agent_run(inbound: InboundMessage, user_id: UUID) -> None` — module-level; opens its OWN `SessionLocal`, loads the user, builds the agent, and calls `process_professional_message`. Best-effort: logs and swallows exceptions. This is what the webhook schedules on `BackgroundTasks`.

Idempotency is enforced by the DB unique constraint: `handle` attempts the insert and treats an `IntegrityError` as a duplicate (rollback → `status="duplicate"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_ingestion_service.py
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.channels.inbound import InboundMessage
from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.models.inbound_message import InboundMessageRecord
from app.models.user import User
from app.services import ingestion_service
from app.services.ingestion_service import IngestionService, dispatch_agent_run

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
PRO_PHONE = "+5551977776666"
LEAD_PHONE = "5551911110000"


def _make(provider_message_id, sender_phone, text="oi"):
    return InboundMessage(
        provider="evolution",
        sender_phone=sender_phone,
        text=text,
        provider_message_id=provider_message_id,
        timestamp=datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc),
        recipient_phone=None,
        raw={"event": "messages.upsert"},
    )


def _purge_inbound(db, *ids):
    db.query(InboundMessageRecord).filter(
        InboundMessageRecord.provider_message_id.in_(ids)
    ).delete(synchronize_session=False)
    db.commit()


def test_known_professional_is_classified_and_recorded(db_user_phone):
    db = SessionLocal()
    try:
        res = IngestionService(db).handle(_make("MID-PRO-1", PRO_PHONE))
        assert res.status == "professional"
        assert res.user_id == DEV_USER_ID
        rec = db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id == "MID-PRO-1"
        ).one()
        assert rec.classification == "professional"
        assert rec.user_id == DEV_USER_ID
    finally:
        _purge_inbound(db, "MID-PRO-1")
        db.close()


def test_unknown_number_is_parked_as_lead():
    db = SessionLocal()
    try:
        res = IngestionService(db).handle(_make("MID-LEAD-1", LEAD_PHONE))
        assert res.status == "lead"
        assert res.user_id is None
        rec = db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id == "MID-LEAD-1"
        ).one()
        assert rec.classification == "lead"
        assert rec.user_id is None
    finally:
        _purge_inbound(db, "MID-LEAD-1")
        db.close()


def test_duplicate_message_is_not_processed_twice():
    db = SessionLocal()
    try:
        first = IngestionService(db).handle(_make("MID-DUP-1", LEAD_PHONE))
        assert first.status == "lead"
        second = IngestionService(db).handle(_make("MID-DUP-1", LEAD_PHONE))
        assert second.status == "duplicate"
        count = db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id == "MID-DUP-1"
        ).count()
        assert count == 1
    finally:
        _purge_inbound(db, "MID-DUP-1")
        db.close()


async def test_dispatch_agent_run_persists_a_turn(db_user_phone, monkeypatch):
    monkeypatch.setattr(ingestion_service, "build_calendar_access", lambda db, user, settings: None, raising=False)

    def _noop(messages, info):
        return ModelResponse(parts=[TextPart("noop")])

    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("resposta via webhook")])

    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop)):
        from app.agents.simplifica_agent import build_simplifica_agent
        agent = build_simplifica_agent()
    monkeypatch.setattr(ingestion_service, "build_simplifica_agent", lambda: agent)

    inbound = _make("MID-RUN-1", PRO_PHONE)
    with agent.override(model=FunctionModel(scripted)):
        await dispatch_agent_run(inbound, DEV_USER_ID)

    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(
            ChatSession.user_id == DEV_USER_ID,
            ChatSession.phone_number == inbound.sender_phone,
        ).first()
        assert session is not None
        msgs = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.asc()).all()
        assert [m.message_type for m in msgs] == ["user", "assistant"]
        assert msgs[1].content == "resposta via webhook"
        db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete(
            synchronize_session=False
        )
        db.query(ChatSession).filter(ChatSession.id == session.id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()
```

Add this fixture to `tests/integration/test_ingestion_service.py` (sets the dev user's phone so `PRO_PHONE` resolves, restores it after):

```python
import pytest


@pytest.fixture
def db_user_phone():
    db = SessionLocal()
    user = db.get(User, DEV_USER_ID)
    previous = user.phone
    user.phone = PRO_PHONE
    db.commit()
    yield
    restore = SessionLocal()
    try:
        u = restore.get(User, DEV_USER_ID)
        u.phone = previous
        restore.commit()
    finally:
        restore.close()
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_ingestion_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.ingestion_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/ingestion_service.py
"""Ingestion orchestrator: idempotency -> classify -> route.

`handle` is synchronous and deterministic (no LLM): it dedupes, resolves the
sender, and records the message. The slow agent run for professionals is run
separately via `dispatch_agent_run` (scheduled on FastAPI BackgroundTasks).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.channels.inbound import InboundMessage
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.inbound_message import InboundMessageRecord
from app.models.user import User
from app.services.agent_runner import process_professional_message
from app.services.calendar_provider import build_calendar_access  # noqa: F401 (patch target for tests)
from app.services.identity_service import resolve_sender

# Imported lazily-style at module scope so tests can monkeypatch it.
from app.agents.simplifica_agent import build_simplifica_agent

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    status: str  # "duplicate" | "professional" | "lead"
    user_id: UUID | None
    record_id: UUID | None


class IngestionService:
    def __init__(self, db: Session):
        self.db = db

    def handle(self, inbound: InboundMessage) -> IngestionResult:
        user = resolve_sender(self.db, inbound.sender_phone)
        classification = "professional" if user is not None else "lead"
        record = InboundMessageRecord(
            provider=inbound.provider,
            provider_message_id=inbound.provider_message_id,
            sender_phone=inbound.sender_phone,
            recipient_phone=inbound.recipient_phone,
            text=inbound.text,
            classification=classification,
            user_id=user.id if user is not None else None,
            raw=inbound.raw,
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            # Unique (provider, provider_message_id) violated -> redelivery.
            self.db.rollback()
            return IngestionResult(status="duplicate", user_id=None, record_id=None)
        self.db.refresh(record)
        return IngestionResult(
            status=classification,
            user_id=user.id if user is not None else None,
            record_id=record.id,
        )


async def dispatch_agent_run(inbound: InboundMessage, user_id: UUID) -> None:
    """Run the professional agent for an already-recorded message.

    Opens its own DB session (it runs after the webhook response, on a
    BackgroundTask). Best-effort: logs and swallows any failure.
    """
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        agent = build_simplifica_agent()
        await process_professional_message(db, agent, user, inbound.text, inbound.sender_phone)
    except Exception:  # noqa: BLE001 - background work must never raise
        logger.warning("agent run for inbound message failed", exc_info=True)
    finally:
        db.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_ingestion_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/ingestion_service.py tests/integration/test_ingestion_service.py
git commit -m "feat(ingestion): idempotent classify-and-route orchestrator"
```

---

### Task 9: Webhook endpoints + config + router registration

**Files:**
- Modify: `app/core/config.py` (add Evolution settings)
- Create: `app/api/webhook_routes.py`
- Modify: `app/main.py` (register webhook router)
- Test: `tests/integration/test_webhook_routes.py`

**Interfaces:**
- Consumes: `EvolutionInboundAdapter` (Task 3), `MetaInboundAdapter` + `verify_meta_handshake` + `valid_meta_signature` (Task 4), `IngestionService` + `dispatch_agent_run` (Task 8), `settings`.
- Produces three routes under router prefix `/webhooks`:
  - `GET /webhooks/whatsapp` — Meta verification handshake (returns the challenge as a plain integer/text or 403).
  - `POST /webhooks/whatsapp` — Meta inbound (verifies signature; parse → handle → maybe schedule agent run).
  - `POST /webhooks/evolution` — Evolution inbound (verifies shared token header; parse → handle → maybe schedule agent run).

Both POST routes always return `{"status": "ok"}` with HTTP 200 for accepted/duplicate/ignored messages (so providers stop redelivering); only auth failures return 403.

**Config additions** in `app/core/config.py`, in the WHATSAPP block (after `WHATSAPP_API_URL`):

```python
    # Meta app secret for X-Hub-Signature-256 verification (optional; disables check if unset)
    WHATSAPP_APP_SECRET: Optional[str] = Field(default=None, env="WHATSAPP_APP_SECRET")

    # =============================================================================
    # EVOLUTION API (default WhatsApp provider)
    # =============================================================================
    EVOLUTION_API_URL: Optional[str] = Field(default=None, env="EVOLUTION_API_URL")
    EVOLUTION_API_KEY: Optional[str] = Field(default=None, env="EVOLUTION_API_KEY")
    EVOLUTION_INSTANCE: Optional[str] = Field(default=None, env="EVOLUTION_INSTANCE")
    EVOLUTION_WEBHOOK_TOKEN: Optional[str] = Field(default=None, env="EVOLUTION_WEBHOOK_TOKEN")
```

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_webhook_routes.py
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.chat_session import ChatMessage, ChatSession
from app.models.inbound_message import InboundMessageRecord
from app.models.user import User

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
PRO_PHONE = "+5551955554444"


def _evolution_payload(message_id, remote_jid, text="quero marcar"):
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


def _purge(message_id):
    db = SessionLocal()
    try:
        db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id == message_id
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_meta_handshake_returns_challenge(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verifytok")
    client = TestClient(app)
    r = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "verifytok", "hub.challenge": "42"},
    )
    assert r.status_code == 200
    assert r.text.strip('"') == "42"


def test_meta_handshake_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verifytok")
    client = TestClient(app)
    r = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "WRONG", "hub.challenge": "42"},
    )
    assert r.status_code == 403


def test_evolution_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", "evotok")
    client = TestClient(app)
    r = client.post(
        "/webhooks/evolution",
        json=_evolution_payload("WH-BAD", "5551911110000@s.whatsapp.net"),
        headers={"X-Webhook-Token": "WRONG"},
    )
    assert r.status_code == 403


def test_evolution_unknown_number_parks_lead(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)  # token check disabled
    client = TestClient(app)
    try:
        r = client.post(
            "/webhooks/evolution",
            json=_evolution_payload("WH-LEAD", "5551911110000@s.whatsapp.net"),
        )
        assert r.status_code == 200
        db = SessionLocal()
        try:
            rec = db.query(InboundMessageRecord).filter(
                InboundMessageRecord.provider_message_id == "WH-LEAD"
            ).one()
            assert rec.classification == "lead"
        finally:
            db.close()
    finally:
        _purge("WH-LEAD")


def test_evolution_known_professional_schedules_agent(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    # point dev user's phone at PRO_PHONE so it resolves
    setup = SessionLocal()
    user = setup.get(User, DEV_USER_ID)
    previous = user.phone
    user.phone = PRO_PHONE
    setup.commit()
    setup.close()

    scheduled = {}

    async def fake_dispatch(inbound, user_id):
        scheduled["user_id"] = user_id
        scheduled["text"] = inbound.text

    # TestClient runs BackgroundTasks synchronously after the response.
    with patch("app.api.webhook_routes.dispatch_agent_run", side_effect=fake_dispatch):
        client = TestClient(app)
        try:
            r = client.post(
                "/webhooks/evolution",
                json=_evolution_payload("WH-PRO", PRO_PHONE + "@s.whatsapp.net"),
            )
            assert r.status_code == 200
            assert scheduled.get("user_id") == DEV_USER_ID
            assert scheduled.get("text") == "quero marcar"
        finally:
            _purge("WH-PRO")
            restore = SessionLocal()
            u = restore.get(User, DEV_USER_ID)
            u.phone = previous
            restore.commit()
            restore.close()


def test_evolution_duplicate_is_acked_without_reprocessing(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    client = TestClient(app)
    try:
        p = _evolution_payload("WH-DUP", "5551911110000@s.whatsapp.net")
        r1 = client.post("/webhooks/evolution", json=p)
        r2 = client.post("/webhooks/evolution", json=p)
        assert r1.status_code == 200 and r2.status_code == 200
        db = SessionLocal()
        try:
            count = db.query(InboundMessageRecord).filter(
                InboundMessageRecord.provider_message_id == "WH-DUP"
            ).count()
            assert count == 1
        finally:
            db.close()
    finally:
        _purge("WH-DUP")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_webhook_routes.py -v`
Expected: FAIL (route 404 / `ModuleNotFoundError` for `app.api.webhook_routes`)

- [ ] **Step 3: Write minimal implementation**

```python
# app/api/webhook_routes.py
"""WhatsApp webhook endpoints (Evolution default, Meta scaffold).

Both POST routes always return 200 for accepted/duplicate/ignored messages so
providers stop redelivering; only authentication failures return 403.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.channels.evolution_adapter import EvolutionInboundAdapter
from app.channels.meta_adapter import (
    MetaInboundAdapter,
    valid_meta_signature,
    verify_meta_handshake,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.services.ingestion_service import IngestionService, dispatch_agent_run

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_evolution = EvolutionInboundAdapter()
_meta = MetaInboundAdapter()

_OK = {"status": "ok"}


def _ingest_and_maybe_schedule(db: Session, inbound, background: BackgroundTasks) -> None:
    result = IngestionService(db).handle(inbound)
    if result.status == "professional" and result.user_id is not None:
        background.add_task(dispatch_agent_run, inbound, result.user_id)


@router.get("/whatsapp")
async def meta_verify(request: Request) -> Response:
    params = request.query_params
    challenge = verify_meta_handshake(
        params.get("hub.mode"),
        params.get("hub.verify_token"),
        params.get("hub.challenge"),
        settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "",
    )
    if challenge is None:
        return Response(status_code=403)
    return PlainTextResponse(challenge)


@router.post("/whatsapp")
async def meta_inbound(
    request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    raw_body = await request.body()
    if not valid_meta_signature(
        raw_body, request.headers.get("X-Hub-Signature-256"), settings.WHATSAPP_APP_SECRET
    ):
        return Response(status_code=403)
    payload = await request.json()
    inbound = _meta.parse(payload)
    if inbound is None:
        return _OK
    _ingest_and_maybe_schedule(db, inbound, background)
    return _OK


@router.post("/evolution")
async def evolution_inbound(
    request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    expected = settings.EVOLUTION_WEBHOOK_TOKEN
    if expected:
        provided = request.headers.get("X-Webhook-Token") or request.query_params.get("token")
        if provided != expected:
            return Response(status_code=403)
    payload = await request.json()
    inbound = _evolution.parse(payload)
    if inbound is None:
        return _OK
    _ingest_and_maybe_schedule(db, inbound, background)
    return _OK
```

Register the router in `app/main.py` — add the import near `from app.api.agent_routes import router as agent_router`:

```python
from app.api.webhook_routes import router as webhook_router
```

and register it WITHOUT the API prefix (webhooks are configured as absolute URLs in the provider dashboards), next to the existing `app.include_router(agent_router, ...)`:

```python
app.include_router(webhook_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_webhook_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py app/api/webhook_routes.py app/main.py tests/integration/test_webhook_routes.py
git commit -m "feat(webhook): Evolution + Meta WhatsApp ingestion endpoints"
```

---

### Task 10: Full-suite + lint verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole suite (excluding live)**

Run: `uv run pytest -m "not live" -q`
Expected: all pass (existing 96 + the new unit/integration tests).

- [ ] **Step 2: Lint**

Run: `uv run ruff check app tests`
Expected: clean.

- [ ] **Step 3: Confirm migrations are linear**

Run: `uv run alembic history | head`
Expected: `0006_inbound_message` follows `0005_chat_session_summary`; single head.

No commit (verification only). Any fix needed is committed under the task it belongs to.

---

## Self-Review

**Spec coverage:**
- Inbound port (DTO + Protocol) → Task 1. ✓
- Evolution adapter (complete) → Task 3. ✓
- Meta adapter (scaffold) + verification → Task 4. ✓
- Phone normalization → Task 2. ✓
- Identity resolution → Task 6. ✓
- `inbound_message` table (idempotency + audit + lead queue) → Task 5. ✓
- Ingestion orchestrator (idempotency → resolve → route) → Task 8. ✓
- Reusable agent core extraction → Task 7. ✓
- Webhook endpoints + per-provider verification + async ack → Task 9. ✓
- Outbound out of scope; no client agent → honored (lead path parks only; no send-back). ✓
- New Evolution config, no hardcoded secrets → Task 9. ✓

**Placeholder scan:** no TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `InboundMessage` fields identical across Tasks 1/3/4/8. `process_professional_message(db, agent, user, text, phone)` defined in Task 7, consumed in Task 8. `IngestionService.handle -> IngestionResult` defined in Task 8, consumed in Task 9. `verify_meta_handshake`/`valid_meta_signature` signatures match between Task 4 and Task 9. ORM class `InboundMessageRecord` consistent across Tasks 5/8/9. ✓
