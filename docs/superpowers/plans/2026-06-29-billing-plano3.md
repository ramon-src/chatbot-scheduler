# Billing (Plano 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the agent track payments and remind clients, configurable per client as monthly or per-session billing.

**Architecture:** Billing lives on the existing `Event.payment_status`; a new per-client `Client.billing_mode` selects monthly vs per-session behavior. Three new billing tools (pure impl + thin wrapper) drive `EventService` helpers; the reminder reuses the outbound port to message the client directly. Verified by unit + deterministic eval (fake outbound) + live scenarios.

**Tech Stack:** Python 3.11+, Pydantic AI, SQLAlchemy 2, Alembic, pydantic_evals, pytest, uv.

## Global Constraints

- Código/identificadores/enums em inglês; mensagens ao profissional e ao cliente em PT-BR.
- Tool contract `{"success": bool, "data": Any, "message": str}`; `message` never contains IDs/JSON/HTML/markdown/URLs.
- Models in schema `simplificapsi`; timezone `America/Sao_Paulo`; week starts Sunday.
- Money stays `Decimal`/`Numeric`; format currency as `f"R$ {value:.2f}"` (no float precision artifacts).
- `Client.billing_mode` ∈ {`per_session`, `monthly`}, default `monthly`. Configured via `create_client`/`update_client`.
- A pending payment = `Event` with `billable=True`, `payment_status in (pending, partial)`, `start_time < now`, excluding series templates.
- A reminder is sent only to the resolved client's own phone and contains only that client's data; degrade (no crash) if no phone or no outbound.
- Evals real LLM gated `RUN_EVAL=1` + `OPENAI_API_KEY`, default `gpt-5.4-mini`, `evaluate_sync(max_concurrency=1)`. Live gated `RUN_LIVE=1`.
- TDD: new behavior starts with a failing test. No secrets in code. Commits never attribute to AI.

---

### Task 1: `Client.billing_mode` (model, migration, schema, service)

**Files:**
- Modify: `app/models/client.py`
- Create: `migrations/versions/0014_client_billing_mode.py`
- Modify: `app/schemas/client.py`
- Modify: `app/services/client_service.py`
- Test: `tests/unit/test_billing_mode_schema.py` (create)
- Test: `tests/integration/test_client_billing_mode.py` (create)

**Interfaces:**
- Produces: `BillingMode` enum (`PER_SESSION="per_session"`, `MONTHLY="monthly"`); `Client.billing_mode` column; `ClientCreate.billing_mode` (default `"monthly"`), `ClientUpdate.billing_mode` (optional), `ClientResponse.billing_mode`; create/update persist it.

- [ ] **Step 1: Write the failing schema test**

Create `tests/unit/test_billing_mode_schema.py`:

```python
"""ClientCreate/Update accept and validate billing_mode."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.client import ClientCreate, ClientUpdate


def _base(**over):
    data = dict(name="Maria Silva", phone="+5551999990000", user_id=uuid.uuid4(),
                invoice_day=10, consult_price=Decimal("200"))
    data.update(over)
    return data


def test_create_defaults_to_monthly():
    c = ClientCreate(**_base())
    assert c.billing_mode == "monthly"


def test_create_accepts_per_session():
    c = ClientCreate(**_base(billing_mode="per_session"))
    assert c.billing_mode == "per_session"


def test_create_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        ClientCreate(**_base(billing_mode="weekly"))


def test_update_billing_mode_optional_and_validated():
    assert ClientUpdate().billing_mode is None
    assert ClientUpdate(billing_mode="monthly").billing_mode == "monthly"
    with pytest.raises(ValidationError):
        ClientUpdate(billing_mode="bogus")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_billing_mode_schema.py -v`
Expected: FAIL — `billing_mode` not a field on the schemas.

- [ ] **Step 3: Add the enum + column to the model**

In `app/models/client.py`, add the import `from enum import Enum` (top) and, above `class Client`:

```python
class BillingMode(str, Enum):
    """How a client is billed."""
    PER_SESSION = "per_session"
    MONTHLY = "monthly"
```

Add the column in the BASIC INFO block (after `consult_price`):

```python
    billing_mode = Column(String(20), nullable=False, server_default="monthly")
```

- [ ] **Step 4: Add the migration**

Create `migrations/versions/0014_client_billing_mode.py`:

```python
"""client billing_mode

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("billing_mode", sa.String(length=20), nullable=False, server_default="monthly"),
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_column("clients", "billing_mode", schema="simplificapsi")
```

(If `0013` is not the current head, set `down_revision` to the actual head reported by `uv run alembic heads`.)

- [ ] **Step 5: Add billing_mode to the schemas**

In `app/schemas/client.py`, add a shared validator and the fields. Near the top-level validators, add a reusable check:

```python
_VALID_BILLING_MODES = {"per_session", "monthly"}


def _check_billing_mode(value):
    if value is not None and value not in _VALID_BILLING_MODES:
        raise ValueError("billing_mode deve ser 'per_session' ou 'monthly'")
    return value
```

In `ClientCreate` add:

```python
    billing_mode: str = Field(default="monthly", description="Modo de cobrança: per_session ou monthly")

    @validator("billing_mode")
    def _validate_billing_mode(cls, v):
        return _check_billing_mode(v)
```

In `ClientUpdate` add:

```python
    billing_mode: Optional[str] = Field(default=None, description="Modo de cobrança: per_session ou monthly")

    @validator("billing_mode")
    def _validate_billing_mode(cls, v):
        return _check_billing_mode(v)
```

In `ClientResponse` add `billing_mode: Optional[str] = Field(default="monthly", ...)` and, in its custom `from_orm`, pass `billing_mode=getattr(client, "billing_mode", "monthly")`.

- [ ] **Step 6: Persist billing_mode in the service**

In `app/services/client_service.py`, `create_client`, add to the `Client(...)` constructor:

```python
                billing_mode=client_data.billing_mode,
```

`update_client` already applies fields via `client_data.dict(exclude_unset=True)` + `setattr`, so `billing_mode` updates flow through automatically — no change needed there.

- [ ] **Step 7: Write the failing integration test (service round-trip)**

Create `tests/integration/test_client_billing_mode.py`:

```python
"""billing_mode persists through create/update via the service."""

import uuid
from decimal import Decimal

import pytest

from app.core.database import SessionLocal
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate
from app.services.client_service import ClientService

DEV_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.mark.asyncio
async def test_create_and_update_billing_mode():
    db = SessionLocal()
    svc = ClientService(db)
    phone = "+5551900000123"
    try:
        created = await svc.create_client(ClientCreate(
            name="Bill Mode", phone=phone, user_id=DEV_USER_ID,
            invoice_day=10, consult_price=Decimal("200"), billing_mode="per_session"))
        row = db.query(Client).filter(Client.id == created.id).first()
        assert row.billing_mode == "per_session"
        await svc.update_client(created.id, DEV_USER_ID, ClientUpdate(billing_mode="monthly"))
        db.refresh(row)
        assert row.billing_mode == "monthly"
    finally:
        db.query(Client).filter(Client.phone == phone).delete(synchronize_session=False)
        db.commit()
        db.close()
```

- [ ] **Step 8: Apply the migration and run the tests**

Run: `make migrate` (or `uv run alembic upgrade head`)
Expected: migration `0014` applies cleanly.

Run: `uv run pytest tests/unit/test_billing_mode_schema.py tests/integration/test_client_billing_mode.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/models/client.py migrations/versions/0014_client_billing_mode.py app/schemas/client.py app/services/client_service.py tests/unit/test_billing_mode_schema.py tests/integration/test_client_billing_mode.py
git commit -m "feat(clients): per-client billing_mode (per_session|monthly, default monthly)"
```

---

### Task 2: Expose billing_mode in client tools + prompt

**Files:**
- Modify: `app/agents/tools/client_tools.py`
- Modify: `app/agents/simplifica_agent.py` (system prompt billing note)
- Test: `tests/unit/test_client_tools_billing_mode.py` (create)

**Interfaces:**
- Consumes: `create_client_impl(deps, name, phone, invoice_day, consult_price, email=None, billing_mode="monthly")`, `update_client_impl(deps, phone, **fields)` (now accepts `billing_mode`).
- Produces: `create_client`/`update_client` agent tools accept `billing_mode`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_client_tools_billing_mode.py`:

```python
"""create_client_impl / update_client_impl thread billing_mode to the service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.tools.client_tools import create_client_impl, update_client_impl


def _deps():
    svc = SimpleNamespace(create_client=AsyncMock(return_value=SimpleNamespace(name="Maria")),
                          update_client=AsyncMock(return_value=SimpleNamespace(name="Maria")),
                          find_client_by_phone=AsyncMock(return_value=SimpleNamespace(id=uuid4(), name="Maria")))
    return SimpleNamespace(client_service=svc, user_id=uuid4())


@pytest.mark.asyncio
async def test_create_passes_billing_mode():
    deps = _deps()
    await create_client_impl(deps, "Maria Silva", "+5551999990000", 10, 200, billing_mode="per_session")
    payload = deps.client_service.create_client.call_args.args[0]
    assert payload.billing_mode == "per_session"


@pytest.mark.asyncio
async def test_update_passes_billing_mode():
    deps = _deps()
    await update_client_impl(deps, "+5551999990000", billing_mode="monthly")
    payload = deps.client_service.update_client.call_args.args[2]
    assert payload.billing_mode == "monthly"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_client_tools_billing_mode.py -v`
Expected: FAIL — impls don't accept/forward `billing_mode`.

- [ ] **Step 3: Thread billing_mode through the impls and wrappers**

In `app/agents/tools/client_tools.py`:

`create_client_impl` — add the parameter and pass it into `ClientCreate`:

```python
async def create_client_impl(
    deps: AgentDeps, name: str, phone: str,
    invoice_day: int, consult_price: float, email: Optional[str] = None,
    billing_mode: str = "monthly",
) -> dict:
```

In the `ClientCreate(...)` construction inside that impl, add `billing_mode=billing_mode,`.

`update_client_impl(deps, phone, **fields)` already forwards arbitrary fields to `ClientUpdate(**fields)` — confirm `billing_mode` passes through; if it builds `ClientUpdate` from an explicit dict, add `billing_mode` to it.

The `create_client` wrapper — add `billing_mode: str = "monthly"` param and pass it:

```python
    @agent.tool
    async def create_client(
        ctx: RunContext[AgentDeps], name: str, phone: str,
        invoice_day: int, consult_price: float, email: Optional[str] = None,
        billing_mode: str = "monthly",
    ) -> dict:
        """Cadastra um cliente. billing_mode: 'monthly' (cobra por mês) ou 'per_session' (por consulta)."""
        return await create_client_impl(ctx.deps, name, phone, invoice_day, consult_price, email, billing_mode)
```

The `update_client` wrapper — add `billing_mode: Optional[str] = None` param and include it in the fields dict passed to `update_client_impl` (only when not None, matching how the other optional fields are handled).

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/unit/test_client_tools_billing_mode.py -v`
Expected: PASS.

- [ ] **Step 5: Add the prompt billing note**

In `app/agents/simplifica_agent.py`, append to `SIMPLIFICA_SYSTEM_PROMPT` (after the COLETA INCREMENTAL / agenda block):

```
COBRANÇA:
- Cada cliente tem um modo de cobrança: "monthly" (cobra uma vez por mês) ou "per_session"
  (cobra por consulta). O padrão é mensal. Se o profissional disser "cobro fulano todo mês",
  use monthly; "por consulta"/"avulso", use per_session. Defina/atualize isso no cadastro do cliente.
- Para marcar pago: em cliente per_session peça a data da consulta; em cliente mensal use o mês.
- Nunca invente valores; use as tools de cobrança para somar pendências e enviar lembretes.
```

- [ ] **Step 6: Run the client-tool unit tests for no regressions**

Run: `uv run pytest tests/unit/test_client_tools_billing_mode.py tests/unit -k client -q`
Expected: PASS (existing client-tool tests still green).

- [ ] **Step 7: Commit**

```bash
git add app/agents/tools/client_tools.py app/agents/simplifica_agent.py tests/unit/test_client_tools_billing_mode.py
git commit -m "feat(clients): set billing_mode via create/update client tools + prompt note"
```

---

### Task 3: EventService billing helpers

**Files:**
- Modify: `app/services/event_service.py`
- Test: `tests/integration/test_event_billing.py` (create)

**Interfaces:**
- Produces: `EventService.set_payment_status(event, status) -> Event`; `EventService.list_pending_payments(user_id, *, client_id=None, start=None, end=None, now) -> list[Event]`.

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_event_billing.py`. Reuse the seeding pattern from `tests/integration/test_event_service.py` (read it first for the session/user/client/calendar fixtures; adapt names to the real fixtures, like the agenda series test did).

```python
"""EventService billing helpers: list pending, set paid."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models.event import Event, EventStatus, PaymentStatus
from app.services.event_service import EventService

TZ = ZoneInfo("America/Sao_Paulo")


def test_list_pending_excludes_future_paid_and_nonbillable(db_session, seed_user_client_calendar):
    user_id, client, calendar = seed_user_client_calendar[:3]
    es = EventService(db_session)
    now = datetime(2026, 6, 29, 12, 0, tzinfo=TZ)

    def _ev(hours_ago, *, paid=False, billable=True):
        start = now - timedelta(hours=hours_ago)
        e = Event(user_id=user_id, client_id=client.id, calendar_id=calendar.id,
                  title="Sessão", start_time=start, end_time=start + timedelta(hours=1),
                  price=Decimal("200"), billable=billable,
                  status=EventStatus.SCHEDULED.value,
                  payment_status=(PaymentStatus.PAID.value if paid else PaymentStatus.PENDING.value))
        db_session.add(e)
        return e

    past_pending = _ev(48)
    _ev(24, paid=True)            # paid -> excluded
    _ev(24, billable=False)       # non-billable -> excluded
    future = Event(user_id=user_id, client_id=client.id, calendar_id=calendar.id,
                   title="Futura", start_time=now + timedelta(hours=24),
                   end_time=now + timedelta(hours=25), price=Decimal("200"),
                   billable=True, status=EventStatus.SCHEDULED.value,
                   payment_status=PaymentStatus.PENDING.value)
    db_session.add(future)
    db_session.commit()

    pending = es.list_pending_payments(user_id, client_id=client.id, now=now)
    ids = {e.id for e in pending}
    assert past_pending.id in ids
    assert future.id not in ids
    assert len(pending) == 1

    es.set_payment_status(past_pending, PaymentStatus.PAID.value)
    db_session.refresh(past_pending)
    assert past_pending.payment_status == PaymentStatus.PAID.value
    assert es.list_pending_payments(user_id, client_id=client.id, now=now) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integration/test_event_billing.py -v`
Expected: FAIL — helpers don't exist.

- [ ] **Step 3: Implement the helpers**

In `app/services/event_service.py`, add:

```python
    def set_payment_status(self, event: Event, status: str) -> Event:
        event.payment_status = status
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_pending_payments(self, user_id: UUID, *, client_id=None, start=None, end=None, now) -> list[Event]:
        """Billable, not-yet-paid sessions that have already occurred (start_time < now).
        Excludes cancelled-status only if non-billable; a billable cancelled no-show still
        counts. Excludes series templates."""
        q = self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.billable == True,  # noqa: E712
                Event.payment_status.in_([PaymentStatus.PENDING.value, PaymentStatus.PARTIAL.value]),
                Event.start_time < now,
                ~and_(Event.is_recurring == True, Event.parent_event_id.is_(None)),  # noqa: E712
            )
        )
        if client_id is not None:
            q = q.filter(Event.client_id == client_id)
        if start is not None:
            q = q.filter(Event.start_time >= start)
        if end is not None:
            q = q.filter(Event.start_time < end)
        return q.order_by(Event.start_time).all()
```

(`PaymentStatus` is already imported in this module.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integration/test_event_billing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/event_service.py tests/integration/test_event_billing.py
git commit -m "feat(billing): EventService set_payment_status + list_pending_payments"
```

---

### Task 4: `mark_paid` + `list_pending_payments` tools

**Files:**
- Create: `app/agents/tools/billing_tools.py`
- Modify: `app/agents/simplifica_agent.py` (register billing tools)
- Test: `tests/unit/test_billing_tools.py` (create)

**Interfaces:**
- Consumes: `_resolve_client` (from `app.agents.tools.calendar_tools`), `EventService.set_payment_status`, `EventService.list_pending_payments`, `EventService.find_client_session_on_date`, `Client.billing_mode`, `PaymentStatus`, `calculate_date_range`.
- Produces: `mark_paid_impl`, `list_pending_payments_impl`, and tools `mark_paid`, `list_pending_payments`; `register_billing_tools(agent)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_billing_tools.py`:

```python
"""mark_paid + list_pending_payments impls (mode-keyed)."""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.tools.billing_tools import list_pending_payments_impl, mark_paid_impl

TZ = "America/Sao_Paulo"


def _client(mode="monthly", name="Maria Silva"):
    return SimpleNamespace(id=uuid4(), name=name, phone="+5551999990000",
                           consult_price=Decimal("200"), billing_mode=mode)


def _deps(client, *, pending=None, session=None):
    es = MagicMock()
    es.list_pending_payments.return_value = pending or []
    es.find_client_session_on_date.return_value = session
    es.set_payment_status.return_value = None
    cs = MagicMock()

    async def _by_phone(phone, user_id):
        return client

    async def _by_name(name, user_id):
        return [client] if client else []

    cs.find_client_by_phone = _by_phone
    cs.find_client_by_name = _by_name
    return SimpleNamespace(event_service=es, client_service=cs, user_id=uuid4(),
                           timezone=TZ, current_datetime=datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo(TZ)))


@pytest.mark.asyncio
async def test_mark_paid_per_session_by_date():
    client = _client(mode="per_session")
    sess = SimpleNamespace(id=uuid4(), price=Decimal("200"))
    deps = _deps(client, session=sess)
    out = await mark_paid_impl(deps, client_phone=client.phone, session_date="2026-06-24")
    assert out["success"] is True
    deps.event_service.set_payment_status.assert_called_once()


@pytest.mark.asyncio
async def test_mark_paid_per_session_without_date_asks():
    client = _client(mode="per_session")
    deps = _deps(client)
    out = await mark_paid_impl(deps, client_phone=client.phone)
    assert out["success"] is False
    assert "data" in out["message"].lower()


@pytest.mark.asyncio
async def test_mark_paid_monthly_marks_all_pending():
    client = _client(mode="monthly")
    pend = [SimpleNamespace(id=uuid4(), price=Decimal("200")),
            SimpleNamespace(id=uuid4(), price=Decimal("200"))]
    deps = _deps(client, pending=pend)
    out = await mark_paid_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert deps.event_service.set_payment_status.call_count == 2
    assert "400" in out["message"]


@pytest.mark.asyncio
async def test_list_pending_for_client_reports_total():
    client = _client()
    pend = [SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client),
            SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client)]
    deps = _deps(client, pending=pend)
    out = await list_pending_payments_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert "400" in out["message"]


@pytest.mark.asyncio
async def test_list_pending_empty():
    client = _client()
    deps = _deps(client, pending=[])
    out = await list_pending_payments_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert "pendente" in out["message"].lower() or "nenhum" in out["message"].lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_billing_tools.py -v`
Expected: FAIL — `billing_tools` does not exist.

- [ ] **Step 3: Implement the billing tools**

Create `app/agents/tools/billing_tools.py`:

```python
"""Billing tools: pure impls + thin @agent.tool wrappers. Tracking on Event.payment_status."""

from datetime import date as _date
from datetime import datetime
from decimal import Decimal

from app.agents.deps import AgentDeps
from app.agents.tools.calendar_tools import _resolve_client
from app.models.event import PaymentStatus
from app.utils.date_range import calculate_date_range


def _unavailable() -> dict:
    return {"success": False, "data": None,
            "message": "Não consigo acessar a cobrança agora. Tente de novo em instantes."}


def _brl(value) -> str:
    return f"R$ {Decimal(str(value or 0)):.2f}"


def _month_window(when: datetime):
    start = when.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start.replace(year=start.year + 1, month=1) if start.month == 12
           else start.replace(month=start.month + 1))
    return start, nxt


def _total(events) -> Decimal:
    return sum((Decimal(str(e.price or 0)) for e in events), Decimal("0"))


async def mark_paid_impl(deps: AgentDeps, *, client_name=None, client_phone=None,
                         session_date=None, month=None) -> dict:
    if deps.event_service is None:
        return _unavailable()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    mode = getattr(client, "billing_mode", "monthly")
    first = client.name.split()[0]

    if mode == "per_session":
        if not session_date:
            return {"success": False, "data": None,
                    "message": f"Qual a data da consulta de {first} que foi paga? (dia/mês)"}
        try:
            day = _date.fromisoformat(session_date)
        except ValueError:
            return {"success": False, "data": None,
                    "message": "Não entendi a data. Use o formato AAAA-MM-DD."}
        event = deps.event_service.find_client_session_on_date(deps.user_id, client.id, day)
        if event is None:
            return {"success": False, "data": None,
                    "message": f"Não encontrei consulta de {first} nessa data."}
        deps.event_service.set_payment_status(event, PaymentStatus.PAID.value)
        return {"success": True, "data": {"client": client.name},
                "message": f"Marquei a consulta de {first} como paga."}

    # monthly
    ref = deps.current_datetime if month is None else datetime.fromisoformat(month)
    start, end = _month_window(ref)
    pending = deps.event_service.list_pending_payments(
        deps.user_id, client_id=client.id, start=start, end=end, now=deps.current_datetime)
    if not pending:
        return {"success": True, "data": {"client": client.name, "count": 0},
                "message": f"{first} não tem consultas em aberto nesse mês."}
    for e in pending:
        deps.event_service.set_payment_status(e, PaymentStatus.PAID.value)
    total = _total(pending)
    return {"success": True, "data": {"client": client.name, "count": len(pending)},
            "message": f"Marquei o mês de {first} como pago: {len(pending)} consulta(s), {_brl(total)}."}


async def list_pending_payments_impl(deps: AgentDeps, *, client_name=None,
                                     client_phone=None, period=None) -> dict:
    if deps.event_service is None:
        return _unavailable()
    start = end = None
    if period:
        try:
            start, end = calculate_date_range(period, deps.current_datetime)
        except ValueError:
            return {"success": False, "data": None,
                    "message": "Não entendi o período. Tente 'este mês' ou 'esta semana'."}

    if client_name or client_phone:
        client, error = await _resolve_client(deps, client_name, client_phone)
        if error:
            return error
        pending = deps.event_service.list_pending_payments(
            deps.user_id, client_id=client.id, start=start, end=end, now=deps.current_datetime)
        first = client.name.split()[0]
        if not pending:
            return {"success": True, "data": {"client": client.name, "count": 0},
                    "message": f"{first} não tem pagamentos pendentes."}
        return {"success": True, "data": {"client": client.name, "count": len(pending)},
                "message": f"{first} tem {len(pending)} consulta(s) em aberto, total {_brl(_total(pending))}."}

    pending = deps.event_service.list_pending_payments(
        deps.user_id, start=start, end=end, now=deps.current_datetime)
    if not pending:
        return {"success": True, "data": {"count": 0},
                "message": "Você não tem pagamentos pendentes."}
    by_client: dict = {}
    for e in pending:
        name = e.client.name if getattr(e, "client", None) else "cliente"
        slot = by_client.setdefault(name, [Decimal("0"), 0])
        slot[0] += Decimal(str(e.price or 0))
        slot[1] += 1
    parts = "; ".join(f"{n.split()[0]}: {c} consulta(s), {_brl(v)}" for n, (v, c) in by_client.items())
    return {"success": True, "data": {"count": len(pending)},
            "message": f"Pagamentos em aberto — {parts}. Total {_brl(_total(pending))}."}
```

- [ ] **Step 4: Register the tools**

Create `register_billing_tools(agent)` at the bottom of `billing_tools.py`:

```python
def register_billing_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def mark_paid(
        ctx: RunContext[AgentDeps], client_name: str | None = None,
        client_phone: str | None = None, session_date: str | None = None,
        month: str | None = None,
    ) -> dict:
        """Marca consulta(s) como pagas. Cliente per_session: informe session_date (AAAA-MM-DD).
        Cliente mensal: usa o mês (month ISO opcional, padrão o mês atual)."""
        return await mark_paid_impl(ctx.deps, client_name=client_name, client_phone=client_phone,
                                    session_date=session_date, month=month)

    @agent.tool
    async def list_pending_payments(
        ctx: RunContext[AgentDeps], client_name: str | None = None,
        client_phone: str | None = None, period: str | None = None,
    ) -> dict:
        """Lista pagamentos em aberto (de um cliente ou de todos), com totais."""
        return await list_pending_payments_impl(ctx.deps, client_name=client_name,
                                                client_phone=client_phone, period=period)
```

In `app/agents/simplifica_agent.py`, import and register:

```python
from app.agents.tools.billing_tools import register_billing_tools
```

and inside `build_simplifica_agent`, after `register_calendar_tools(agent)`:

```python
    register_billing_tools(agent)
```

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/unit/test_billing_tools.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Run the agent wiring test for no regressions**

Run: `uv run pytest -p no:warnings -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/agents/tools/billing_tools.py app/agents/simplifica_agent.py tests/unit/test_billing_tools.py
git commit -m "feat(billing): mark_paid + list_pending_payments tools (mode-keyed)"
```

---

### Task 5: `send_payment_reminder` + outbound on deps

**Files:**
- Modify: `app/agents/deps.py` (add `outbound`)
- Modify: `app/services/agent_runner.py` (wire `EvolutionOutboundAdapter` into `build_agent_deps`)
- Modify: `app/agents/tools/billing_tools.py` (add reminder impl + tool)
- Test: `tests/unit/test_payment_reminder.py` (create)

**Interfaces:**
- Consumes: `OutboundAdapter`/`OutboundMessage` (`app.channels.outbound`), `EvolutionOutboundAdapter`, `EventService.list_pending_payments`, `_resolve_client`.
- Produces: `AgentDeps.outbound: OutboundAdapter | None`; `send_payment_reminder_impl`; tool `send_payment_reminder`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_payment_reminder.py`:

```python
"""send_payment_reminder_impl sends a client-scoped reminder via outbound."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.tools.billing_tools import send_payment_reminder_impl

TZ = "America/Sao_Paulo"


class _FakeOutbound:
    provider = "fake"

    def __init__(self):
        self.sent = []

    def send(self, message) -> bool:
        self.sent.append(message)
        return True


def _client(mode="monthly"):
    return SimpleNamespace(id=uuid4(), name="Maria Silva", phone="+5551999990000",
                           consult_price=Decimal("200"), billing_mode=mode)


def _deps(client, *, pending, outbound):
    es = MagicMock()
    es.list_pending_payments.return_value = pending
    cs = MagicMock()

    async def _by_phone(phone, user_id):
        return client

    cs.find_client_by_phone = _by_phone
    return SimpleNamespace(event_service=es, client_service=cs, outbound=outbound, user_id=uuid4(),
                           timezone=TZ, current_datetime=datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo(TZ)))


@pytest.mark.asyncio
async def test_reminder_sent_to_client_with_amount():
    client = _client()
    ob = _FakeOutbound()
    pend = [SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client),
            SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client)]
    deps = _deps(client, pending=pend, outbound=ob)
    out = await send_payment_reminder_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert len(ob.sent) == 1
    assert ob.sent[0].to_phone == client.phone
    assert "400" in ob.sent[0].text
    assert "Maria" in ob.sent[0].text


@pytest.mark.asyncio
async def test_reminder_nothing_pending_sends_nothing():
    client = _client()
    ob = _FakeOutbound()
    deps = _deps(client, pending=[], outbound=ob)
    out = await send_payment_reminder_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert ob.sent == []
    assert "em aberto" in out["message"].lower() or "pendente" in out["message"].lower()


@pytest.mark.asyncio
async def test_reminder_no_outbound_degrades():
    client = _client()
    pend = [SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client)]
    deps = _deps(client, pending=pend, outbound=None)
    out = await send_payment_reminder_impl(deps, client_phone=client.phone)
    assert out["success"] is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_payment_reminder.py -v`
Expected: FAIL — `send_payment_reminder_impl` does not exist.

- [ ] **Step 3: Add `outbound` to AgentDeps**

In `app/agents/deps.py`, add to `AgentDeps` (after `event_service`):

```python
    outbound: "OutboundAdapter | None" = field(default=None)
```

and under `TYPE_CHECKING`:

```python
    from app.channels.outbound import OutboundAdapter
```

- [ ] **Step 4: Wire outbound in build_agent_deps**

In `app/services/agent_runner.py`, `build_agent_deps`, build the adapter best-effort and pass it:

```python
    outbound = None
    try:
        from app.channels.evolution_outbound import EvolutionOutboundAdapter
        outbound = EvolutionOutboundAdapter(settings)
    except Exception:  # noqa: BLE001 - never break the chat on outbound setup
        outbound = None
```

and add `outbound=outbound,` to the `AgentDeps(...)` construction.

- [ ] **Step 5: Implement the reminder**

In `app/agents/tools/billing_tools.py`, add the import and impl:

```python
from app.channels.outbound import OutboundMessage
```

```python
async def send_payment_reminder_impl(deps: AgentDeps, *, client_name=None,
                                     client_phone=None, period=None) -> dict:
    if deps.event_service is None:
        return _unavailable()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    first = client.name.split()[0]
    if not getattr(client, "phone", None):
        return {"success": False, "data": None,
                "message": f"Não tenho o telefone de {first} para enviar o lembrete."}
    if deps.outbound is None:
        return {"success": False, "data": None,
                "message": "O envio de mensagens não está disponível agora. Tente mais tarde."}

    start = end = None
    if period:
        try:
            start, end = calculate_date_range(period, deps.current_datetime)
        except ValueError:
            return {"success": False, "data": None,
                    "message": "Não entendi o período. Tente 'este mês'."}
    pending = deps.event_service.list_pending_payments(
        deps.user_id, client_id=client.id, start=start, end=end, now=deps.current_datetime)
    if not pending:
        return {"success": True, "data": {"client": client.name, "count": 0},
                "message": f"{first} não tem pagamentos em aberto."}

    total = _total(pending)
    mode = getattr(client, "billing_mode", "monthly")
    if mode == "per_session" and len(pending) == 1:
        when = pending[0].start_time.astimezone(__import__("zoneinfo").ZoneInfo(deps.timezone)).strftime("%d/%m")
        text = (f"Olá {first}! Passando pra lembrar do pagamento da sua consulta de {when}, "
                f"no valor de {_brl(total)}. Qualquer coisa, estou à disposição.")
    else:
        text = (f"Olá {first}! Passando pra lembrar do pagamento de {len(pending)} consulta(s), "
                f"no total de {_brl(total)}. Qualquer coisa, estou à disposição.")
    ok = deps.outbound.send(OutboundMessage(to_phone=client.phone, text=text))
    if not ok:
        return {"success": False, "data": None,
                "message": f"Não consegui enviar o lembrete para {first} agora. Tente de novo."}
    return {"success": True, "data": {"client": client.name, "count": len(pending)},
            "message": f"Enviei o lembrete de pagamento para {first}."}
```

Register the tool inside `register_billing_tools`:

```python
    @agent.tool
    async def send_payment_reminder(
        ctx: RunContext[AgentDeps], client_name: str | None = None,
        client_phone: str | None = None, period: str | None = None,
    ) -> dict:
        """Envia um lembrete de pagamento ao WhatsApp do próprio cliente, com o total em aberto."""
        return await send_payment_reminder_impl(ctx.deps, client_name=client_name,
                                                client_phone=client_phone, period=period)
```

- [ ] **Step 6: Run it to verify it passes**

Run: `uv run pytest tests/unit/test_payment_reminder.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Full unit suite for no regressions**

Run: `uv run pytest -p no:warnings -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/agents/deps.py app/services/agent_runner.py app/agents/tools/billing_tools.py tests/unit/test_payment_reminder.py
git commit -m "feat(billing): send_payment_reminder to client via outbound port"
```

---

### Task 6: Billing eval suite (fake outbound)

**Files:**
- Modify: `evals/fakes.py` (add `FakeOutboundAdapter`)
- Modify: `evals/harness.py` (seed payment_status/billing_mode, inject fake outbound, snapshot payment_status)
- Modify: `evals/evaluators.py` (DbState `session_paid_for_client`)
- Create: `evals/datasets/billing.py`
- Modify: `evals/run.py` (`--suite billing`)
- Modify: `Makefile` (`eval-billing`)
- Test: `tests/unit/test_eval_evaluators.py` (extend; read it first to match style)

**Interfaces:**
- Produces: `FakeOutboundAdapter` (records sends); harness seeds `payment_status`/`billable` on events and `billing_mode` on clients, injects `deps.outbound`, snapshots event `payment_status`; `DbState` key `session_paid_for_client`; `build_billing_dataset()`.

- [ ] **Step 1: Write the failing evaluator test**

Append to `tests/unit/test_eval_evaluators.py` (match the file's existing `DbSnapshot`/`CaseResult`/`_ctx` helpers):

```python
def test_dbstate_session_paid_for_client():
    from evals.evaluators import DbState
    from evals.harness import CaseResult, DbSnapshot
    snap = DbSnapshot(events=[{"status": "scheduled", "client": "Maria Silva",
                               "payment_status": "paid", "start_time": "x"}])
    result = CaseResult(tool_calls=[], final_output="", transcript=[], db=snap,
                        tokens=0, latency_ms=0, model="m")
    ctx = type("C", (), {"output": result})()
    assert DbState(check={"session_paid_for_client": "Maria"}).evaluate(ctx) is True
    assert DbState(check={"session_paid_for_client": "Joana"}).evaluate(ctx) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_eval_evaluators.py -k session_paid -v`
Expected: FAIL.

- [ ] **Step 3: Extend DbState + FakeOutboundAdapter**

In `evals/evaluators.py`, inside `DbState.evaluate` before `return True`:

```python
        if "session_paid_for_client" in c:
            name = c["session_paid_for_client"]
            if not any(
                (ev.get("client") or "") and name in ev["client"] and ev.get("payment_status") == "paid"
                for ev in db.events
            ):
                return False
```

In `evals/fakes.py`, add:

```python
class FakeOutboundAdapter:
    """Records outbound sends; never hits the network."""
    provider = "fake"

    def __init__(self) -> None:
        self.sent = []

    def send(self, message) -> bool:
        self.sent.append(message)
        return True
```

- [ ] **Step 4: Extend the harness**

In `evals/harness.py`:

1. `_apply_setup` event seeding — pass payment fields when present:

```python
            es.record_event(
                user_id=EVAL_USER_ID, client_id=client.id, title=f"Sessão - {client.name}",
                start=start, end=end, google_event_id=f"seed-{i}",
                is_recurring=bool(ev.get("recurring", False)),
                recurrence_rule=ev.get("recurrence_rule"),
                price=client.consult_price,
            )
```

Capture the created event from `record_event` and, when the seed sets `payment_status` or `billable`, apply them. The full seeding loop body becomes:

```python
            created_ev = es.record_event(
                user_id=EVAL_USER_ID, client_id=client.id, title=f"Sessão - {client.name}",
                start=start, end=end, google_event_id=f"seed-{i}",
                is_recurring=bool(ev.get("recurring", False)),
                recurrence_rule=ev.get("recurrence_rule"),
                price=client.consult_price,
            )
            if "payment_status" in ev:
                created_ev.payment_status = ev["payment_status"]
            if "billable" in ev:
                created_ev.billable = ev["billable"]
            if "payment_status" in ev or "billable" in ev:
                db.commit()
```

(This replaces the prior `es.record_event(...)` call shown in step 1 above — do not keep both.)

2. Client seeding — pass `billing_mode`:

```python
        db.add(Client(
            user_id=EVAL_USER_ID, name=c["name"], phone=c["phone"],
            invoice_day=c.get("invoice_day", 10),
            consult_price=Decimal(str(c.get("consult_price", 200))),
            billing_mode=c.get("billing_mode", "monthly"), is_active=True,
        ))
```

3. `_snapshot` events — add `payment_status`:

```python
         "payment_status": e.payment_status,
```

4. `run_case` pro branch — inject a fake outbound alongside the fake calendar:

```python
    from evals.fakes import FakeCalendarService, FakeOutboundAdapter
    fake_calendar = FakeCalendarService()
    fake_outbound = FakeOutboundAdapter()
```

and after `deps = build_agent_deps(...)` in the pro branch:

```python
                deps.calendar_service = fake_calendar
                deps.outbound = fake_outbound
```

- [ ] **Step 5: Create the billing dataset**

Create `evals/datasets/billing.py`:

```python
"""Billing eval cases: mark paid, list pending, reminder (fake outbound)."""

from __future__ import annotations

from pydantic_evals import Case, Dataset

from evals.evaluators import DbState, NoLeakage, ToolSelected
from evals.harness import CaseInputs

_MONTHLY = {
    "clients": [{"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10,
                 "consult_price": 200, "billing_mode": "monthly"}],
    "events": [{"client": "Maria Silva", "start": "2026-06-10T10:00:00-03:00", "duration": 60,
                "payment_status": "pending", "billable": True},
               {"client": "Maria Silva", "start": "2026-06-17T10:00:00-03:00", "duration": 60,
                "payment_status": "pending", "billable": True}],
}
_PER_SESSION = {
    "clients": [{"name": "Carla Dias", "phone": "+5551988887777", "invoice_day": 5,
                 "consult_price": 180, "billing_mode": "per_session"}],
    "events": [{"client": "Carla Dias", "start": "2026-06-24T09:00:00-03:00", "duration": 60,
                "payment_status": "pending", "billable": True}],
}


def build_billing_dataset() -> Dataset:
    cases = [
        Case(
            name="billing_marca_pago_mensal",
            inputs=CaseInputs(agent="pro", setup=_MONTHLY,
                              messages=["a Maria Silva pagou o mês"]),
            evaluators=[ToolSelected(tool="mark_paid"),
                        DbState(check={"session_paid_for_client": "Maria"}), NoLeakage()],
        ),
        Case(
            name="billing_lista_pendentes",
            inputs=CaseInputs(agent="pro", setup=_MONTHLY,
                              messages=["quem está com pagamento em aberto?"]),
            evaluators=[ToolSelected(tool="list_pending_payments"), NoLeakage()],
        ),
        Case(
            name="billing_lembrete",
            inputs=CaseInputs(agent="pro", setup=_MONTHLY,
                              messages=["manda um lembrete de pagamento pra Maria Silva"]),
            evaluators=[ToolSelected(tool="send_payment_reminder"), NoLeakage()],
        ),
        Case(
            name="billing_marca_pago_por_sessao",
            inputs=CaseInputs(agent="pro", setup=_PER_SESSION,
                              messages=["a Carla Dias pagou a consulta do dia 24 de junho"]),
            evaluators=[ToolSelected(tool="mark_paid"),
                        DbState(check={"session_paid_for_client": "Carla"}), NoLeakage()],
        ),
    ]
    return Dataset(name="billing", cases=cases)
```

- [ ] **Step 6: Wire `--suite billing` + Makefile**

In `evals/run.py`, add an `elif suite == "billing":` branch importing `from evals.datasets.billing import build_billing_dataset`, setting `dataset = build_billing_dataset()`, reusing the `run_case` task (same as agent/agenda). Add `"billing"` to the argparse `--suite` choices.

In `Makefile`, after `eval-agenda`:

```makefile
eval-billing: ## Rodar o eval de cobrança (LLM real + outbound fake; usage: make eval-billing [MODEL=gpt-5.4-mini] [CASE=<substr>])
	@RUN_EVAL=1 $(UV) run python -m evals.run --suite billing --model $(or $(MODEL),gpt-5.4-mini) $(if $(CASE),--case $(CASE),)
```

- [ ] **Step 7: Unit gate + real eval run**

Run: `uv run pytest -p no:warnings -q`
Expected: PASS.

Run: `make eval-billing`
Expected: the billing suite runs against `gpt-5.4-mini`; record per-case PASS/FAIL verbatim. Do NOT weaken assertions — a model/tool gap is a real finding.

- [ ] **Step 8: Commit**

```bash
git add evals/fakes.py evals/harness.py evals/evaluators.py evals/datasets/billing.py evals/run.py Makefile tests/unit/test_eval_evaluators.py
git commit -m "feat(evals): billing suite (mark paid / list pending / reminder) + fake outbound"
```

---

### Task 7: Live billing scenarios

**Files:**
- Modify: `tests/live/test_agent_live_scenarios.py` (un-skip + align the 3 billing scenarios)

**Interfaces:**
- Consumes: the `live` fixture; the shipped tool names `mark_paid`, `list_pending_payments`, `send_payment_reminder`.

- [ ] **Step 1: Read the three skipped billing tests**

Read `test_billing_mark_paid`, `test_billing_list_pending`, `test_billing_send_reminder` in `tests/live/test_agent_live_scenarios.py`, and the `live` fixture in `tests/live/conftest.py` (note `live.send`/`live.send_memory`, `live.client_name`, `live.client_phone`, `live.tool_returns`, `live.db`).

- [ ] **Step 2: Un-skip and align the billing scenarios**

Remove the `@pytest.mark.skip(...)` on the three billing tests. Align each body to the shipped behavior:
- `test_billing_mark_paid`: create a past session for `live.client_name`, then "marca como paga a consulta de <data> da <cliente>"; assert `mark_paid` was called (`live.tool_returns(result, "mark_paid")`) and the mirror event's `payment_status == "paid"`.
- `test_billing_list_pending`: with a pending session seeded, "quem está em aberto?"; assert `list_pending_payments` was called and the reply names the client.
- `test_billing_send_reminder`: "manda um lembrete pra <cliente>"; assert `send_payment_reminder` was called and the reply confirms ("Enviei"). The reminder goes to `live.client_phone` (the controlled test number) — never a real patient.

Use `live.send_memory` where a later turn references a session created earlier in the same test. Pick session hours that don't collide with other scenarios (the module-scoped fixture accumulates events) — use a dedicated hour (e.g. 7h) for billing-created sessions.

- [ ] **Step 3: Collect + non-live suite**

Run: `uv run pytest tests/live/test_agent_live_scenarios.py --collect-only -q`
Expected: clean collection, no import/parse errors.

Run: `uv run pytest -p no:warnings -q`
Expected: PASS (live tests skip without `RUN_LIVE`).

- [ ] **Step 4: Commit**

```bash
git add tests/live/test_agent_live_scenarios.py
git commit -m "test(billing): enable live mark-paid / list-pending / reminder scenarios"
```

- [ ] **Step 5: Run the live billing scenarios (real)**

Run: `RUN_LIVE=1 uv run pytest tests/live/test_agent_live_scenarios.py -k billing -p no:warnings -v`
Expected: the three billing scenarios run against the real LLM (Google not required for billing; the reminder hits the controlled test number). Record per-test PASS/FAIL verbatim. If `RUN_LIVE`/credentials are unavailable here, report that the controller must run it; do NOT mark green on collection alone. Do not weaken assertions.

---

## Self-Review

**Spec coverage:**
- `Client.billing_mode` (column/migration/schema/service) → Task 1; exposed in client tools + prompt → Task 2.
- `EventService` billing helpers (set_payment_status, list_pending_payments) → Task 3.
- `mark_paid` (mode-keyed) + `list_pending_payments` tools → Task 4.
- `AgentDeps.outbound` wiring + `send_payment_reminder` (client-scoped, degrade paths) → Task 5.
- Eval coverage (fake outbound, seed payment_status/billing_mode, DbState payment, dataset, --suite billing, run) → Task 6.
- Live: un-skip + align the 3 billing scenarios + run → Task 7.
- Out-of-scope (PIX, aggregated invoices, fiscal) → not implemented.

**Placeholder scan:** none — every code step has full content; Task 6 Step 4 shows the full seeding-loop body to use. Tasks referencing "read the existing file first" (Task 3 fixtures, Task 6 evaluator test, Task 7 bodies) are concrete reuse instructions, not deferred work.

**Type consistency:** `billing_mode` string enum values `per_session`/`monthly` consistent across model/schema/tools/dataset; `mark_paid_impl(deps, *, client_name, client_phone, session_date, month)`, `list_pending_payments_impl(deps, *, client_name, client_phone, period)`, `send_payment_reminder_impl(deps, *, client_name, client_phone, period)` consistent between Tasks 4/5 and the eval/live tool names; `EventService.list_pending_payments(user_id, *, client_id, start, end, now)` and `set_payment_status(event, status)` consistent between Task 3 and callers; `FakeOutboundAdapter`/`DbState.session_paid_for_client` consistent between Task 6 definition and use.
