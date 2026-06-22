# WhatsApp Ingestion (provider-agnostic) — Design

**Date:** 2026-06-21
**Status:** Approved (brainstorming)
**Slice of:** Plano 4 (segunda metade — ingestão de canal). Builds on top of the
session-memory slice (`feat/session-memory`).

## Goal

Receive inbound WhatsApp messages from more than one provider (Evolution API as
the default, Meta Cloud API as a scaffolded second provider), normalize them into
a single internal format that the agent never sees the provider through, and route
each message by sender identity: a number linked to a professional account runs the
existing agent flow; an unlinked number is recorded as a lead and parked.

## Scope

**In scope:**
- A provider-agnostic inbound port (`InboundMessage` + `InboundAdapter`).
- Evolution API inbound adapter (complete).
- Meta Cloud API inbound adapter (scaffold behind the same port).
- Phone normalization for matching sender numbers against `User.phone`.
- Identity resolution (`resolve_sender`).
- An ingestion orchestrator that does idempotency → resolve → route.
- A reusable agent-processing core extracted from the current `/agent/message` route.
- An `inbound_message` table (idempotency + audit + lead queue).
- Webhook endpoints with per-provider verification/security.

**Out of scope (explicitly deferred):**
- **Outbound.** The professional's agent reply is persisted in chat history but is
  NOT sent back over WhatsApp in this slice. A dedicated outbound port/adapter is a
  separate future slice.
- **Client/lead-facing agent.** Unlinked numbers are parked; no agent runs for them.
  The `inbound_message` rows classified `lead` are the queue a future client agent
  will consume.

## Architecture — ports & adapters (hexagonal)

The core (agent, memory, identity) never knows which provider delivered a message.
Each provider has an inbound adapter that translates the raw webhook payload into a
single internal DTO, `InboundMessage`. An orchestrator (`IngestionService`) consumes
`InboundMessage`, resolves identity, and routes.

```
Webhook (Evolution | Meta)
        │  raw provider payload
        ▼
InboundAdapter.parse(payload) ──► InboundMessage  (normalized; 'provider' never leaks into the agent)
        ▼
IngestionService.handle(inbound)
        ├─ idempotency  (provider_message_id already seen? → ack and stop)
        ├─ resolve_sender(phone) → User | None
        ├─ User  → process_professional_message(...)   [reuses the /agent/message core]
        └─ None  → record lead and park (no agent run)
```

## Components / files

| File | Responsibility |
|---|---|
| `app/channels/inbound.py` | `InboundMessage` dataclass + `InboundAdapter` Protocol |
| `app/channels/evolution_adapter.py` | Evolution payload → `InboundMessage` (complete) |
| `app/channels/meta_adapter.py` | Meta Cloud payload → `InboundMessage` (scaffold) |
| `app/channels/phone.py` | phone normalization for matching |
| `app/services/identity_service.py` | `resolve_sender(db, phone) -> User \| None` |
| `app/services/ingestion_service.py` | orchestrator `handle(inbound)`: idempotency → resolve → route |
| `app/services/agent_runner.py` | extracted core `process_professional_message(...)` reused by HTTP + webhook |
| `app/models/inbound_message.py` | inbound-message table (idempotency + audit + lead queue) |
| `app/api/webhook_routes.py` | `GET/POST /webhooks/whatsapp` (Meta), `POST /webhooks/evolution` |
| `migrations/versions/0006_inbound_message.py` | creates `inbound_message` |

### `InboundMessage` (the internal DTO)

```python
@dataclass(frozen=True)
class InboundMessage:
    provider: str            # "evolution" | "meta" — used by the ingestion layer only, never by the agent
    sender_phone: str        # normalized, digits-only canonical form
    text: str                # message body
    provider_message_id: str # for idempotency
    timestamp: datetime      # provider-reported send time (tz-aware)
    recipient_phone: str | None  # the business number the message was sent to
    raw: dict                # original payload, kept for audit
```

### `InboundAdapter` (the port)

```python
class InboundAdapter(Protocol):
    provider: str
    def parse(self, payload: dict) -> InboundMessage | None: ...
    # Returns None for non-message events (delivery/read statuses, presence, etc.)
```

### `inbound_message` table

A single table serves idempotency, audit, and the lead queue — chosen over a
dedicated rich `Lead` entity (YAGNI while no agent consumes leads).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `provider` | varchar | "evolution" \| "meta" |
| `provider_message_id` | varchar | unique with `provider` |
| `sender_phone` | varchar | normalized |
| `recipient_phone` | varchar null | business number |
| `text` | text | |
| `classification` | varchar | "professional" \| "lead" |
| `user_id` | UUID null | FK to `simplificapsi.users` when professional |
| `raw` | jsonb | original payload |
| `received_at` | timestamptz | server default now() |

Unique constraint: `(provider, provider_message_id)`.

## Processing model — asynchronous ack + idempotency

WhatsApp providers redeliver when they do not get a fast 200, and the agent (LLM)
takes seconds; processing synchronously risks timeout → redelivery → duplicate
processing.

The webhook endpoint:
1. parses the payload via the provider's adapter;
2. writes the `inbound_message` row with an idempotency check (synchronous, fast) —
   if `(provider, provider_message_id)` already exists, returns 200 and stops;
3. returns **200** immediately;
4. schedules the heavy work (identity resolution + agent run for professionals) via
   FastAPI `BackgroundTasks`, which opens its own `SessionLocal`.

The unique key on `(provider, provider_message_id)` guards against redelivery races.

Tests exercise `IngestionService.handle()` directly (deterministic) plus a
webhook-level test asserting a fast 200.

## Identity & phone normalization

`resolve_sender(db, phone)` matches the normalized inbound sender number against the
normalized `User.phone`. Linked → professional; unlinked → lead.

Normalization (`app/channels/phone.py`) reduces both sides to a canonical digits-only
form: strips `@s.whatsapp.net`/`@c.us` suffixes, non-digits, and a leading `+`;
assumes Brazil DDI `55` when absent. **Known limitation:** the Brazilian mobile
"9th digit" can make two representations of the same line differ; the normalizer
handles the common case (compare on canonical 12/13-digit `55DDXXXXXXXXX`) and the
limitation is documented for a later hardening pass.

## Error handling & security

- **Meta verification:** `GET /webhooks/whatsapp` echoes `hub.challenge` when
  `hub.verify_token == WHATSAPP_WEBHOOK_VERIFY_TOKEN`; `POST` validates
  `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret). Invalid
  token/signature → 403.
- **Evolution verification:** a shared-token header (`EVOLUTION_WEBHOOK_TOKEN`, new
  config) → 403 when it does not match.
- **Idempotency:** unique `(provider, provider_message_id)`; duplicate → 200 and stop.
- **Non-message payloads** (delivery/read status, presence) → `parse` returns `None`
  → 200 and ignore.
- **Agent/persistence failure:** best-effort, same pattern already adopted in the
  memory slice — log, never break the webhook (always 200, so providers do not
  redeliver forever).
- **New config (all optional, no hardcoded secrets):** `EVOLUTION_API_URL`,
  `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`, `EVOLUTION_WEBHOOK_TOKEN`.

## Refactor: shared agent-processing core

The current `/agent/message` route inlines: `get_or_create_session` → `recent_messages`
→ `to_model_messages` → build deps → `agent.run` → `_persist_turn` → `_maybe_update_summary`.
Extract this into `app/services/agent_runner.py::process_professional_message(db, agent,
user, text, phone) -> str`, and have both the HTTP route and the webhook ingestion call
it (DRY). The unknown-user one-shot path in the HTTP route stays as is.

## Testing strategy

**Unit**
- Evolution adapter: a real sample payload → expected `InboundMessage`.
- Meta adapter: a sample payload → expected `InboundMessage`.
- Phone normalization: multiple formats incl. `@s.whatsapp.net` suffix and BR 9th-digit.
- `resolve_sender`: match and no-match.
- Idempotency: duplicate `(provider, provider_message_id)` is not processed twice.

**Integration**
- POST Evolution payload from a known professional number → agent runs, turn persisted,
  `inbound_message.classification == "professional"`, `user_id` set.
- POST from an unknown number → `inbound_message.classification == "lead"`, agent does
  NOT run.
- Duplicate `provider_message_id` → no reprocessing.
- Meta `GET` verification handshake returns the challenge for a valid token; 403 otherwise.
- Invalid Evolution/Meta token/signature → 403.

## Success criteria

- An Evolution webhook from a registered professional drives the full agent flow and
  persists a turn, with the agent unaware of the provider.
- An unknown number is parked as a lead without running the agent.
- Redelivered webhooks never double-process.
- Meta is reachable through the same port (handshake + parse) without being the default.
- No outbound delivery and no client-facing agent are introduced.
