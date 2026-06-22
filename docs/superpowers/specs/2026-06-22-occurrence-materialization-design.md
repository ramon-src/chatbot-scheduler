# Occurrence Materialization + Billable Flag — Design (Slice 3a)

**Date:** 2026-06-22
**Status:** Approved (brainstorming)
**Part of:** Plano 3 (billing). This is sub-slice **3a** — the agenda-layer data
foundation that billing (sub-slice 3b) sits on top of. 3b is out of scope here.

## Goal

Make each session of a recurring series an independent, listable, cancellable
row in the Postgres mirror (occurrence materialization), and record the
professional's charge-or-not decision per session via a `billable` flag — so a
later billing slice can track payment per occurrence and so cancelled/no-show
sessions can be charged or waived at the professional's discretion.

## Why (the legacy "duplicated events" problem, solved differently)

The legacy duplicated events in the DB so a billing record survived the
calendar's realized/cancelled state. Our architecture already keeps the Postgres
mirror row after cancellation (the mirror is not deleted), so we do not need to
duplicate for *single* events. The genuine gap is **recurring series**: today a
series is stored as ONE mirror row (`is_recurring=true` + `recurrence_rule`,
`start_time` = first occurrence), so individual sessions cannot carry their own
`payment_status`/`billable`, and `list_events`/`cancel_event` only ever see the
series in the week of its first occurrence. Materializing per-occurrence rows
fixes both the billing prerequisite and that pre-existing listing limitation.

## Scope

**In scope:**
- `Event` columns: `parent_event_id`, `occurrence_date`, `billable`.
- Lazy, idempotent occurrence materialization from the recurrence rule.
- `list_events` shows materialized occurrences + singles (templates and cancelled
  excluded); recurring sessions appear in every week they occur.
- `cancel_event` cancels a specific occurrence (or single) and records the charge
  decision (`billable`); Google single-instance cancel is best-effort.
- New `set_session_charge` tool to adjust `billable` after the fact.
- Stamp `price` on single-event creation and on every materialized occurrence.

**Out of scope (→ slice 3b):**
- `Client.payment_model`, `billing_service`, payment tools
  (`register_payment`, `list_pending_payments`, `client_billing_summary`).

**Out of scope (deferred entirely):**
- Bidirectional Google sync; full Google-instance reconciliation. The Postgres
  mirror remains authoritative for agent reads/cancels (the v1 stance).

## Data model — `Event` additions

| Column | Type | Notes |
|---|---|---|
| `parent_event_id` | UUID null, FK `simplificapsi.events.id` ondelete CASCADE, indexed | set on occurrence rows → series template row |
| `occurrence_date` | Date null, indexed | the occurrence's calendar date |
| `billable` | Boolean, not null, server_default `true` | whether this session counts for billing |

Unique constraint `uq_event_occurrence` on `(parent_event_id, occurrence_date)` —
makes materialization idempotent. Postgres unique indexes treat NULLs as
distinct, so singles and templates (NULL `parent_event_id`) never collide.

**Row taxonomy after this slice:**
- **Single session:** `is_recurring=false`, `parent_event_id=null`. A billable
  session.
- **Series template:** `is_recurring=true`, `parent_event_id=null`,
  `recurrence_rule` set. NOT a session — excluded from listings and (later)
  billing. It is the expansion source.
- **Occurrence:** `parent_event_id` set, `occurrence_date` set,
  `is_recurring=false`. A billable session belonging to a series.

Existing pre-3a recurring rows become templates automatically (they already have
`is_recurring=true`, `parent_event_id` is NULL by the new column's default). Their
first occurrence is materialized lazily like any other. No data migration of
existing rows is required.

## Occurrence materialization

`EventService.ensure_occurrences(user_id, range_start, range_end) -> int`
(returns count materialized):

1. Load series templates for the user (`is_recurring=true`,
   `parent_event_id IS NULL`, `status != cancelled`) whose active window overlaps
   `[range_start, range_end]`.
2. For each template, expand its `recurrence_rule` (RRULE) into occurrence start
   datetimes within `[max(template.start_time, range_start), min(until or
   range_end, range_end)]`, in the professional's timezone. Use
   `dateutil.rrule.rrulestr` (add `python-dateutil` if not already a dependency).
3. For each occurrence datetime, upsert an occurrence row (idempotent on
   `(parent_event_id, occurrence_date)`): `parent_event_id=template.id`,
   `occurrence_date`, `start_time`=occurrence dt, `end_time`=start +
   (template duration), `title`, `client_id`, `calendar_id`,
   `price = template.price or client.consult_price`, `status=scheduled`,
   `billable=true`, `payment_status=pending`, `is_recurring=false`,
   `google_event_id=null` (the Google series event covers the slot; per-instance
   Google ids are not stored).
4. Commit. Skipping already-present `(parent, occurrence_date)` pairs keeps it
   safe to call on every read.

Materialization is bounded by the queried range — open-ended series are never
fully expanded.

## Tool / behavior changes (`app/agents/tools/calendar_tools.py`)

- **`create_event`** stamps `price = client.consult_price` on the recorded single
  event (today it records `price=None`).
- **`list_events`** calls `ensure_occurrences(range)` then lists sessions in the
  range: occurrences + singles, excluding templates
  (`is_recurring=true AND parent_event_id IS NULL`) and excluding `cancelled`.
- **`cancel_event`** gains a `charge: bool | None = None` parameter (the
  professional's intent). It resolves the client, finds the single non-cancelled
  session for that client in the period (now including occurrences), and:
  - sets `status=cancelled`;
  - sets `billable = charge if charge is not None else False` (default: a
    cancellation is not charged);
  - best-effort cancels the Google side: for a single, the existing
    `calendar_service.cancel_event(google_event_id)`; for an occurrence,
    `calendar_service.cancel_occurrence(parent.google_event_id,
    occurrence.start_time)` (new, best-effort). Failure is logged/swallowed; the
    mirror cancellation stands (consistent with the existing dual-write stance).
- **New `set_session_charge(client_name|client_phone, session_date, charge)`**
  tool + `set_session_charge_impl`: find the client's session on `session_date`
  (occurrence by `occurrence_date`, or single by `start_time` date), set
  `billable=charge`, return a confirmation message. Missing client/session →
  `{success: false}` with an ID-free message.

## Google service addition

`GoogleCalendarService.cancel_occurrence(series_google_event_id, occurrence_start)`
— best-effort cancel of one instance of a recurring Google event (via the
instances API: locate the instance at `occurrence_start`, patch its status to
`cancelled`). Raised exceptions are caught by the caller and swallowed; the
mirror is authoritative. If the instance cannot be located, it is a no-op.

## Tool contract & guard-rails (unchanged conventions)

- Every tool returns `{"success": bool, "data": Any, "message": str}`; `message`
  never contains IDs/JSON/URLs.
- Cancel/charge require an existing client; ambiguity (more than one session in
  the period) asks for the exact day, as today.
- Timezone fixed `America/Sao_Paulo`; all datetimes tz-aware.

## Testing

**Unit — `ensure_occurrences`:**
- Weekly series over a 3-week range materializes one row per week with correct
  dates/times; running twice does not duplicate (idempotent).
- Respects `UNTIL` (no occurrences past it) and the range bounds.
- Occurrence rows carry `price` (from template/client) and `billable=true`.

**Unit / integration — tools:**
- `list_events`: a weekly series appears in week 2 and week 3 (regression for the
  one-row limitation); the template row never appears; a cancelled occurrence
  does not appear.
- `create_event` stamps `price` on the single event.
- `cancel_event`: cancels the correct occurrence; `billable` follows `charge`
  (default cancellation → `billable=false`, "cobra mesmo assim" → `true`); Google
  side is best-effort (mocked).
- `set_session_charge`: flips `billable`; unknown client/session → ID-free
  failure message.

## Success criteria

- A weekly recurring client's sessions are individually listed and cancellable,
  each with its own `billable`/`payment_status`/`price`.
- Cancelling a session records whether it is still charged.
- Materialization is idempotent and bounded by the queried period.
- No billing logic is introduced (that is slice 3b); the data is now billing-ready.
