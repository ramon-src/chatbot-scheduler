# Billing (Plano 3) — Design

**Date:** 2026-06-29
**Status:** Approved (design); pending implementation plan
**Owner components:** `app/models/client.py`, `app/schemas/client.py`, `app/services/event_service.py`, `app/agents/tools/billing_tools.py` (new) + `client_tools.py`, `app/agents/deps.py`, `app/services/agent_runner.py`, `evals/`, `tests/live/`

## Problem

The product covers clients and agenda but not billing — the third domain in
CLAUDE.md (clientes → agenda → cobrança → fiscal). The agent cannot mark a
session paid, tell the professional who owes, or send a payment reminder. Three
live scenarios are skip-marked "Plano 3 — cobrança não implementado".

The billing primitives already exist on the `Event` row: `payment_status`
(`PaymentStatus`: pending/paid/partial/refunded/cancelled), `price`, `billable`.
The `Client` has `invoice_day` (monthly due day) and `consult_price` (per-session
price). There is no dedicated payment model, and none is needed.

## Goal

Let the agent track payments and remind clients, configurable per client as
either monthly or per-session billing.

## Decisions (locked during brainstorming)

- **Billing mode is per client**, stored on `Client.billing_mode` (`per_session | monthly`), **default `monthly`**. Configured conversationally via `create_client`/`update_client` (the LLM maps "todo mês"/"por consulta"/"avulso" to the enum).
- **`mark_paid` granularity follows the client's mode**: monthly → mark all the month's pending billable sessions paid; per_session → mark the session on a given date paid.
- **`send_payment_reminder` sends directly to the client's WhatsApp** via the outbound port. Tasteful PT-BR text, no IDs/links, never exposes other clients' data.
- **Tracking only — no real payment (PIX/simple-charge)** this slice.
- **No dedicated payment model**; billing lives on `Event.payment_status`.

## Scope

**In scope:** `Client.billing_mode` (column + migration + schema + client-tool exposure), three billing tools (`mark_paid`, `list_pending_payments`, `send_payment_reminder`), `EventService` billing helpers, `AgentDeps.outbound` wiring, and three test layers (unit, eval, live).

**Out of scope (deferred):** PIX/simple-charge payment links and webhooks; partial-payment workflows beyond reading `PARTIAL` status; installments; aggregated invoices/receipts; fiscal (Receita Saúde).

## Data model

- New column `Client.billing_mode`: `String`, not null, `server_default="monthly"`, values `per_session | monthly` (a `BillingMode` str-Enum in `app/models/client.py`). Alembic migration adds it with the server default so existing clients become `monthly`.
- A **pending payment** = an `Event` that is `billable=True`, `payment_status in (pending, partial)`, has already occurred (`start_time < now`), and is not a series template. Cancelled-but-billable (no-show charged) sessions count as pending. Materialized occurrences count; templates do not.
- A session's amount is `Event.price` (falls back to the client's `consult_price` when null, as occurrence materialization already does).

## Tools (`app/agents/tools/billing_tools.py`)

Pure impl + thin `@agent.tool` wrapper, tool contract `{"success","data","message"}`, PT-BR messages, no IDs/JSON/markdown/URLs.

### `mark_paid_impl(deps, *, client_name=None, client_phone=None, session_date=None, month=None)`
- Resolve client via the shared `_resolve_client`.
- **per_session client:** require `session_date` (AAAA-MM-DD); find that client's session on that date; set `payment_status=paid`. If missing date, ask for it.
- **monthly client:** use `month` (or the current month); mark all the client's pending billable sessions in that month paid; report how many / total.
- Message examples: "Marquei a consulta da Maria de 24/06 como paga." / "Marquei junho da Maria como pago (4 consultas, R$ 800)."

### `list_pending_payments_impl(deps, *, client_name=None, client_phone=None, period=None)`
- Without a client: list all clients with pending sessions — per-client total + grand total.
- With a client: that client's pending detail. monthly clients aggregate by month; per_session clients list each session.
- Message: "A Maria tem 2 consultas em aberto, total R$ 400; o João tem 1, R$ 180." Empty → "Você não tem pagamentos pendentes."

### `send_payment_reminder_impl(deps, *, client_name=None, client_phone=None, period=None)`
- Resolve client; compute their pending amount (mode-aware).
- Build a tasteful reminder; send to `client.phone` via `deps.outbound`. monthly → month + total; per_session → session date(s) + amount.
- If `deps.outbound` is None or the client has no phone → degrade with a clear message (no crash). If nothing pending → say so, send nothing.
- Returns confirmation to the professional: "Enviei o lembrete de pagamento para a Maria."
- The reminder text shows ONLY that client's data. Example: "Olá Maria! Passando pra lembrar do pagamento da sua consulta de 24/06, no valor de R$ 200. Qualquer coisa, estou à disposição."

## Support changes

- **`EventService`**: `set_payment_status(event, status) -> Event`; `list_pending_payments(user_id, *, client_id=None, start=None, end=None, now) -> list[Event]` (filters billable, pending/partial, occurred, non-template). A helper to find a client's session on a date already exists (`find_client_session_on_date`); reuse or extend it to include cancelled-billable.
- **`AgentDeps`**: add `outbound: OutboundAdapter | None = field(default=None)`. `build_agent_deps` wires `EvolutionOutboundAdapter(settings)` (best-effort; never breaks the chat if construction fails). Tests/eval inject a fake.
- **`Client` schema (`app/schemas/client.py`)**: `ClientCreate`/`ClientUpdate` accept optional `billing_mode` (validated against the enum; create defaults to `monthly`).
- **`client_tools.py`**: `create_client` and `update_client` wrappers expose `billing_mode` so the agent can set/change it; impls pass it through to the service.
- **`build_simplifica_agent`**: register the new billing tools.
- **System prompt**: a short billing section so the agent knows the mode controls how it bills, asks for a session date only for per-session clients, and never invents amounts.

## Testing

1. **Unit** (`tests/unit/`): impl tests with fake deps (SimpleNamespace/MagicMock), including a **fake outbound** asserting `send` is called with the client's phone and a reminder containing the amount; mode-keyed `mark_paid` (per_session by date, monthly by month); `list_pending_payments` totals; degrade paths (no outbound, no phone, nothing pending). `EventService` billing helpers get focused tests. `billing_mode` round-trips through `ClientCreate`/`update`.
2. **Evals** (deterministic, real LLM, gated `RUN_EVAL=1`): harness seeds events with `payment_status`/`billable` and clients with `billing_mode`; inject a fake outbound on the eval deps; add a `DbState` payment check (e.g. a client's session is `paid`); new `evals/datasets/billing.py` cases — mark a session paid, list pending, send reminder (assert tool selected + fake outbound called) — run via a `--suite billing` + `make eval-billing`.
3. **Live** (`RUN_LIVE=1`): un-skip `test_billing_mark_paid`, `test_billing_list_pending`, `test_billing_send_reminder` in `test_agent_live_scenarios.py`; align their assertions to the shipped tool names/messages and mode behavior. The reminder live test must target a controlled client phone (the test client), not a real patient.

## Architecture & boundaries

- Billing tools follow the existing pure-impl + wrapper pattern; only `EventService` and `Client` schema/model gain billing surface. No new layer, no payment provider.
- Outbound reuses the existing `OutboundAdapter` port and `EvolutionOutboundAdapter` — the reminder is just another outbound message; the agent never knows the provider.
- The fake outbound (tests/eval) implements the `OutboundAdapter` Protocol; production never imports it.

## Constraints (inherited, binding)

- Código/identificadores/enums em inglês; mensagens ao usuário e ao cliente em PT-BR.
- Tool contract `{"success","data","message"}`; message never contains IDs/JSON/HTML/markdown/URLs.
- Models in schema `simplificapsi`; timezone `America/Sao_Paulo`; week starts Sunday.
- Money handling stays `Decimal`/`Numeric`; never float-format currency in a way that leaks precision artifacts.
- Reminder to a client must expose only that client's own data; never batch other clients' info into one message.
- Evals real LLM gated `RUN_EVAL=1` + `OPENAI_API_KEY`, default `gpt-5.4-mini`, `evaluate_sync(max_concurrency=1)`. Live gated `RUN_LIVE=1` + service account.
- No secrets in code; commits never attribute to AI.

## Risks

- **Sending to the wrong person.** The reminder hits a real client's WhatsApp. Mitigated: send only to the resolved client's stored phone, only that client's data, degrade if no phone, and the live test uses the controlled test-client number.
- **Mode ambiguity.** The LLM must map free-text to `per_session|monthly`; default `monthly` covers the unspecified case. Eval cases cover both modes.
- **"Occurred" boundary.** Pending excludes future sessions; uses `deps.current_datetime` consistently so eval/live are deterministic.

## Success criteria

- Professional can set a client's billing mode in conversation; it persists.
- `mark_paid` flips the right session(s) to `paid` per the client's mode.
- `list_pending_payments` reports accurate per-client and total amounts, mode-aware.
- `send_payment_reminder` delivers a tasteful, client-scoped reminder to the client's WhatsApp and confirms to the professional.
- Unit + deterministic billing eval suite green; the three live billing scenarios pass (real Google not required for billing; outbound hits the test number).
