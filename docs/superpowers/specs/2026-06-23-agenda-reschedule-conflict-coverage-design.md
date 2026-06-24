# Agenda: Reschedule, Conflict Detection & Full Coverage — Design

**Date:** 2026-06-23
**Status:** Approved (design); pending implementation plan
**Owner components:** `app/agents/tools/calendar_tools.py`, `app/services/event_service.py`, `evals/`, `tests/live/`

## Problem

The agenda is functional (create one-off / recurring, list by period, cancel) but two product gaps remain, and test coverage is uneven:

1. **No reschedule.** `EventService.update_event(event, *, title, start, end)` exists but is not exposed as an agent tool — the agent cannot move an appointment.
2. **No conflict awareness.** The agent will happily double-book the professional at an overlapping time with no warning.
3. **Evals don't cover agenda.** The eval harness seeds only clients; `calendar_service` is `None` for the eval principal, so agenda tools return "not connected" and no agenda case can run.
4. **Live agenda coverage is partly dormant.** `tests/live/test_agent_live_scenarios.py` has READY agenda scenarios kept skip-marked ("enable when we run the live battery"), and there are no explicit persistence/round-trip assertions.

## Goal

Add reschedule + conflict detection to the agenda, then cover the whole agenda
(old and new behavior) with deterministic evals (fake calendar) and a real
Google-backed live integration battery.

## Decisions (locked during brainstorming)

- **Conflict policy:** detect-and-warn, never block. Create the event anyway and append a warning to the success message when an overlap exists.
- **Conflict window:** any active (`SCHEDULED`) event of the professional whose `[start_time, end_time)` interval overlaps the new event's interval. The professional's own calendar — two clients in the same slot is the real conflict.
- **Reschedule scope:** single events AND whole recurring series. Single-occurrence-of-a-series reschedule is out of scope.
- **Eval calendar:** deterministic fake (no Google). Real Google verification lives in the live battery.
- **Live battery:** enable the READY agenda scenarios, add persistence round-trip tests, and run the real battery this session (free quota).

## Scope

**In scope:** reschedule tool, conflict detection, fake-calendar eval support + agenda eval cases, live agenda coverage (enable READY + new round-trips + run).

**Out of scope:** single-occurrence-of-series reschedule; conflict policies other than warn; billing (Plano 3); any change to the create/list/cancel happy paths beyond appending conflict warnings.

---

## Phase 1 — Product: reschedule + conflict detection

### Conflict detection

New pure helper in `calendar_tools.py`:

```
def _find_overlaps(deps, start, end, *, exclude_event_id=None) -> list[Event]
```

- Queries `deps.event_service.list_events_in_range(user_id, day_start, day_end)` for the day(s) spanned, keeps events with `status == SCHEDULED`, drops `exclude_event_id` (so a reschedule does not conflict with itself), and returns those whose `[start_time, end_time)` overlaps `[start, end)`.
- Overlap test: `existing.start_time < end and start < existing.end_time`.

Wired into `create_event_impl`, `create_recurring_event_impl` (checks the first occurrence), and `reschedule_event_impl`. On overlap, the tool still creates/moves and returns `success: True`, but:
- `data` carries `{"conflict": true, "conflict_with": "<client first name>"}`;
- `message` appends a plain-text warning, e.g. `"Atenção: você já tem <Nome> nesse horário."` — no IDs, no markdown.

No-overlap path is unchanged.

### Reschedule tool

New impl + thin `@agent.tool` wrapper, following the existing pattern:

```
async def reschedule_event_impl(
    deps, *, client_name=None, client_phone=None,
    period="this_week", new_start_time: datetime,
    duration_minutes: int | None = None,
) -> dict
```

- Guards: `calendar_service`/`event_service` present (`_not_connected()` otherwise).
- Resolve client via `_resolve_client`. Find the single matching event via a new shared helper `_find_single_event_for_client(deps, client, period)` — extracted from the duplicated find/disambiguate logic currently inside `cancel_event_impl` (0 → "não encontrei", >1 → "qual o dia exato?"). `cancel_event_impl` is refactored to use it (behavior identical).
- Compute `new_end = new_start_time + (duration_minutes or default_consult_minutes)`.
- Conflict check via `_find_overlaps(deps, new_start_time, new_end, exclude_event_id=event.id)`.
- **Single event:** Google `update_event(event.google_event_id, start=…, end=…)` first (source of truth), then `event_service.update_event(event, start=new_start, end=new_end)`. Google failure → degrade with a retry message and do not touch the mirror.
- **Whole recurring series** (`event.is_recurring` true, or `event.parent_event_id` set → resolve to the template): update the series template's `start_time`/`end_time` and the Google series event's start/end, then delete future *materialized* occurrence rows (`parent_event_id == template.id` and `start_time >= now`, status `SCHEDULED`) so they re-materialize from the new template on the next `ensure_occurrences`. Past and cancelled occurrences are left untouched. `EventService` gains a helper for this re-materialization reset (e.g. `reschedule_series(template, new_start, new_end)`).
- Success message: `"Remarquei <Nome> para <data/hora>."` plus any conflict warning.

### Tests (Phase 1)

Unit, TDD red→green, in `tests/unit/test_calendar_tools.py` (or a focused new module), using the existing `SimpleNamespace`/`MagicMock` fake-deps pattern:
- overlap helper: overlapping, adjacent (no overlap), excluded-self, cancelled-ignored;
- create with conflict → success + warning in message + `data.conflict`;
- reschedule single → `update_event` called with new times, success message;
- reschedule with conflict → success + warning;
- reschedule unknown/ambiguous client → same errors as cancel;
- reschedule whole series → template times updated + future occurrences reset.

---

## Phase 2 — Evals: agenda cases with a fake calendar

### FakeCalendarService

New deterministic test double (in `evals/`) implementing the surface the tools call: `create_event(summary, start, end, recurrence=None) -> {"id": "<synthetic>"}`, `update_event(event_id, **changes) -> dict`, `cancel_event(event_id)`, `cancel_occurrence(series_id, occurrence_start)`, `list_events(start, end) -> []`, and `build_weekly_rrule(weekdays, until) -> str`. Synthetic ids are deterministic (e.g. `f"fake-{counter}"`), no network.

### Harness changes (`evals/harness.py`)

- `_ensure_eval_user` (or `_apply_setup`) also ensures a primary `Calendar` row for the eval principal, so `event_service.record_event` can resolve a calendar.
- `run_case` injects the fake: after `build_agent_deps`, set `deps.calendar_service = FakeCalendarService()` for the `pro` agent (the real `event_service` stays — it writes the Postgres mirror the asserts read).
- `_apply_setup` gains optional `events` seeding (client_name, start offset, duration, recurring) so list/cancel/reschedule cases have something to act on.
- `_snapshot` events include `start_time` (iso) and the client name, so eval asserts can check the moved time / which client.
- `_purge` already deletes the eval principal's events — confirm it covers the new Calendar row too.

### New evaluator(s)

If needed, a small `DbState` extension (or a new check key) to assert an event exists for a client at/around an expected local time, and that a reschedule changed the stored `start_time`.

### Dataset cases (`evals/datasets/`)

Agenda suite (deterministic, ToolSelected + DbState + NoLeakage): schedule one-off; schedule recurring; list this week; list empty period; cancel; homonym-asks-for-phone; **reschedule**; **conflict-warns** (seed an event, schedule an overlapping one, assert the second still creates and the message warns). Gated by `RUN_EVAL=1`, run via `make eval-fast`.

---

## Phase 3 — Live integration: persistent agenda (real Google)

Uses the existing `live` fixture (`tests/live/conftest.py`, real service account, real cleanup), gated by `RUN_LIVE=1`.

1. **Enable READY scenarios** in `test_agent_live_scenarios.py`: remove the skip on `test_schedule_with_explicit_duration`, `test_list_empty_period_says_so`, `test_homonym_requires_phone`, `test_cancel_ambiguous_asks_for_day`.
2. **Enable now-built FEATURE scenarios:** `test_reschedule_event` and `test_conflict_detection_warns` (un-skip, adjust assertions to the warn-not-block behavior).
3. **New persistence/round-trip tests** (new module `tests/live/test_agent_live_persistence.py`):
   - create via agent → event present in the Postgres mirror AND listed back by the agent at the correct local time; re-fetch in a fresh session still shows it (persistence);
   - cancel via agent → gone from the mirror and the Google event is cancelled (verify via the calendar service);
   - reschedule via agent → mirror `start_time` updated AND Google event reflects the new time.
4. **Run the battery** (`RUN_LIVE=1` real Google + OpenAI) this session and record per-test PASS/FAIL honestly. A model/tool gap is a real finding, not a reason to weaken an assertion.

---

## Architecture & boundaries

- Conflict and reschedule stay inside the calendar tools (pure impl + thin wrapper); the only service-layer additions are the series re-materialization reset on `EventService`. No new layers, no change to the agent's reasoning loop.
- `_find_single_event_for_client` deduplicates logic shared by cancel and reschedule (DRY).
- The fake calendar lives in `evals/` (test-only); production code never imports it.
- Dual-write ordering and best-effort compensation mirror the existing create/cancel conventions (Google first as source of truth; mirror failure degrades, never 500s the chat).

## Constraints (inherited, binding)

- Código/identificadores em inglês; mensagens ao usuário em PT-BR.
- Tool contract `{"success", "data", "message"}`; `message` never contains IDs/JSON/HTML/markdown/URLs.
- Models in schema `simplificapsi`; timezone fixed `America/Sao_Paulo`; week starts Sunday.
- Evals: real LLM, gated `RUN_EVAL=1` + `OPENAI_API_KEY`, default `gpt-5.4-mini`, `evaluate_sync(max_concurrency=1)`. Live: gated `RUN_LIVE=1` + service account.
- No secrets in code; commits never attribute to AI.

## Risks

- **Whole-series reschedule** is the most complex piece (re-materialization, Google series semantics). Mitigated by: keeping past/cancelled occurrences untouched, resetting only future SCHEDULED occurrences, and covering it with both a unit test and a live test.
- **Live flakiness / quota** — the live battery hits real Google + OpenAI; isolated by the per-user `live` fixture cleanup and gated behind `RUN_LIVE`.
- **Conflict false-negatives** if `list_events_in_range` does not materialize recurring occurrences in the window — call `ensure_occurrences` before the overlap query, as cancel/list already do.

## Success criteria

- Agent can reschedule single and whole-series appointments; both stores reflect the new time.
- Agent warns (without blocking) when a new/moved appointment overlaps an existing one.
- Deterministic agenda eval suite passes (fake calendar), covering create/list/cancel/reschedule/conflict.
- Live battery (real Google) green for the enabled scenarios and the new persistence round-trips.
