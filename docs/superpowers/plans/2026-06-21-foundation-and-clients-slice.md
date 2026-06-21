# SimplificaPsi Agent — Plano 1: Fundação + Fatia de Clientes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir a fundação do sistema de agentes (LLM com fallback + observabilidade + agente único Pydantic AI) e a primeira fatia vertical funcional — gestão de clientes ponta-a-ponta via HTTP, substituindo o esqueleto mockado.

**Architecture:** Um único agente Pydantic AI (`SimplificaAgent`) com tools de cliente. Cada tool é um wrapper fino sobre uma função-impl pura (testável isolada) que chama o `ClientService` existente. Modelo LLM vem de um `FallbackModel` portado do `rooster-platform`. Deps tipadas (`AgentDeps`) carregam usuário/sessão/data. Resposta final é texto livre PT-BR; tools têm I/O tipado.

**Tech Stack:** Python 3.11+ · Pydantic AI · Pydantic v2 · SQLAlchemy · FastAPI · Alembic · pytest · OpenAI + OpenRouter (via FallbackModel)

## Global Constraints

- **Linguagem do código/identificadores:** inglês. Mensagens ao usuário final: Português do Brasil.
- **Models vivem no schema Postgres `simplificapsi`** (`__table_args__ = {"schema": "simplificapsi"}`).
- **Nunca commitar segredos** — `.env`, `credentials.json`, `token.json` já estão no `.gitignore`.
- **Sem atribuição de IA** em mensagens de commit (regra do CLAUDE.md do usuário).
- **Toda tool retorna `dict`** no formato `{"success": bool, "data": Any, "message": str}`. A `message` nunca contém IDs/JSON.
- **Timezone fixo:** `America/Sao_Paulo`.
- **Telefone:** validado via `phonenumbers` (região default `BR`); multi-país fica deferido (fora deste plano).
- **Regra existente mantida:** nome de cliente exige nome + sobrenome (≥2 palavras) — herdada do schema atual.
- **TDD:** todo comportamento novo começa por um teste que falha. Commits frequentes, um por task.
- **Pasta de testes:** `tests/unit/` e `tests/integration/` (já existem).

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `app/agents/foundation/llm.py` | `get_llm_model()` (FallbackModel) + `get_llm_run_metadata()` — portados do rooster-platform |
| `app/agents/foundation/__init__.py` | re-export de `get_llm_model`, `get_llm_run_metadata` |
| `app/core/config.py` | + `OPENROUTER_API_KEY`, `SIMPLIFICA_AGENT_MODEL`, `TIMEZONE` |
| `app/models/client.py` | + colunas `invoice_day`, `consult_price` |
| `app/schemas/client.py` | `ClientCreate` + `invoice_day`/`consult_price`; corrige `from_orm` |
| `app/services/client_service.py` | `create_client` persiste `invoice_day`/`consult_price` |
| `migrations/versions/0002_client_billing_fields.py` | Alembic: adiciona as duas colunas |
| `app/agents/deps.py` | `AgentDeps` (deps tipadas do agente) |
| `app/agents/simplifica_agent.py` | `build_simplifica_agent()` + system prompt |
| `app/agents/tools/client_tools.py` | impl puras + wrappers `@agent.tool` de cliente |
| `app/api/agent_routes.py` | `POST {API_PREFIX}/agent/message` |
| `tests/unit/test_foundation_llm.py` | testes de `llm.py` |
| `tests/unit/test_client_tools.py` | testes das impl de tools |
| `tests/unit/test_simplifica_agent.py` | teste de wiring do agente (FunctionModel) |
| `tests/integration/test_agent_message_endpoint.py` | teste do endpoint |

**Removido deste plano (esqueleto antigo, tratado na Task 1):** `app/agents/calendar_agent.py`, `app/agents/client_agent.py`, `app/agents/agent_manager.py`, `app/agents/workflow.py`, e os `test_*.py` soltos na raiz do repo.

---

### Task 1: Limpeza do esqueleto mockado

**Files:**
- Delete: `app/agents/calendar_agent.py`, `app/agents/client_agent.py`, `app/agents/agent_manager.py`, `app/agents/workflow.py`
- Delete (raiz do repo): `test_client_agent_real.py`, `test_phase5_simple.py`, `test_phase5_simple_v2.py`, `test_client_simple.py`, `test_phase2.py`, `test_phase4_simple.py`, `test_simple.py`, `test_simple_agent.py`, `test_client_phase4.py`, `fix_agent_tools.py`, `create_test_user.py`
- Delete (docs de scratch): `DOCKER_FIX_RESULTS.md`, `AGENT_CORRECTIONS_RESULTS.md`, `OPENAI_TEST_RESULTS.md`, `TEST_RESULTS.md`, `PHASE4_RESULTS.md`
- Modify: `app/agents/__init__.py` (esvaziar exports que apontam para arquivos removidos)

**Interfaces:**
- Produces: pasta `app/agents/` limpa, sem agentes mockados, pronta para a nova fundação.

- [ ] **Step 1: Confirmar que nada importa os módulos a remover**

Run: `grep -rn "from app.agents.workflow\|from app.agents.calendar_agent\|from app.agents.client_agent\|from app.agents.agent_manager\|import workflow" app/ --include="*.py"`
Expected: nenhuma linha fora dos próprios arquivos a deletar. Se houver import em `app/main.py` ou `app/api/`, anotar para ajustar no Step 2.

- [ ] **Step 2: Remover arquivos e limpar `app/agents/__init__.py`**

Apague os arquivos listados. Deixe `app/agents/__init__.py` assim:

```python
"""SimplificaPsi agents package."""
```

Se o Step 1 achou imports em `app/main.py`/rotas, comente/remova essas linhas e qualquer rota que monte o `SimplificaPsiWorkflow` (será substituída na Task 8).

- [ ] **Step 3: Garantir que a aplicação ainda importa**

Run: `python -c "import app.main"`
Expected: sem `ModuleNotFoundError`/`ImportError`. (Se faltar `.env`, exporte vars mínimas ou rode com `ENVIRONMENT=test` conforme o conftest.)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove mocked agent skeleton and scratch test files"
```

---

### Task 2: Config — chaves de modelo e timezone

**Files:**
- Modify: `app/core/config.py`
- Modify: `env.example`
- Test: `tests/unit/test_config_agent_settings.py`

**Interfaces:**
- Produces: `settings.OPENROUTER_API_KEY: Optional[str]`, `settings.SIMPLIFICA_AGENT_MODEL: str` (default `"gpt-5.4-mini"`), `settings.TIMEZONE: str` (default `"America/Sao_Paulo"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config_agent_settings.py
from app.core.config import settings

def test_agent_settings_have_defaults():
    assert settings.SIMPLIFICA_AGENT_MODEL  # non-empty
    assert settings.TIMEZONE == "America/Sao_Paulo"
    # OPENROUTER_API_KEY is optional, attribute must exist
    assert hasattr(settings, "OPENROUTER_API_KEY")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config_agent_settings.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'SIMPLIFICA_AGENT_MODEL'`

- [ ] **Step 3: Add settings**

In `app/core/config.py`, inside `class Settings`, after the OPENAI block add:

```python
    # =============================================================================
    # OPENROUTER (fallback provider for LLM)
    # =============================================================================
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, env="OPENROUTER_API_KEY")

    # =============================================================================
    # AGENT
    # =============================================================================
    SIMPLIFICA_AGENT_MODEL: str = Field(default="gpt-5.4-mini", env="SIMPLIFICA_AGENT_MODEL")
    TIMEZONE: str = Field(default="America/Sao_Paulo", env="TIMEZONE")
```

In `env.example` add:

```
OPENROUTER_API_KEY=
SIMPLIFICA_AGENT_MODEL=gpt-5.4-mini
TIMEZONE=America/Sao_Paulo
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config_agent_settings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py env.example tests/unit/test_config_agent_settings.py
git commit -m "feat: add OpenRouter + agent model/timezone settings"
```

---

### Task 3: Fundação LLM — `get_llm_model` (FallbackModel)

**Files:**
- Create: `app/agents/foundation/__init__.py`
- Create: `app/agents/foundation/llm.py`
- Test: `tests/unit/test_foundation_llm.py`

**Interfaces:**
- Produces:
  - `get_llm_model(model_name: str, temperature: float = 0.3, timeout: int = 30) -> FallbackModel`
  - `get_llm_run_metadata(result: Any) -> Optional[dict]`

**Dependências:** confirme que `pydantic-ai` já está no `pyproject.toml` (o esqueleto usa `pydantic_ai`). Se faltar o provider OpenRouter, rode `uv add "pydantic-ai-slim[openai,openrouter]"` ou `uv add pydantic-ai`. Verifique com `python -c "from pydantic_ai.models.fallback import FallbackModel"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_foundation_llm.py
from pydantic_ai.models.fallback import FallbackModel
from app.agents.foundation import get_llm_model

def test_get_llm_model_returns_fallback():
    model = get_llm_model("gpt-5.4-mini", temperature=0.1, timeout=15)
    assert isinstance(model, FallbackModel)

def test_unknown_model_falls_back_to_default():
    model = get_llm_model("nonexistent-model")
    assert isinstance(model, FallbackModel)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_foundation_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.foundation'`

- [ ] **Step 3: Port the module**

Copie `shared/utils/llm.py` do `rooster-platform` para `app/agents/foundation/llm.py` (mantendo `get_llm_model`, `get_llm_run_metadata`, `get_token_usage`, `get_model_name_and_provider`, `get_prompt`). Crie `app/agents/foundation/__init__.py`:

```python
"""LLM foundation: resilient model selection + run metadata."""

from .llm import get_llm_model, get_llm_run_metadata

__all__ = ["get_llm_model", "get_llm_run_metadata"]
```

Se algum import do OpenRouter falhar no ambiente, mantenha apenas as branches OpenAI no `get_llm_model` por ora (o fallback default `gpt-4.1-mini` cobre os testes); as branches OpenRouter podem ser reativadas quando a chave existir.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_foundation_llm.py -v`
Expected: PASS (2 passed). Os testes só checam o *tipo* — não fazem chamada de rede.

- [ ] **Step 5: Commit**

```bash
git add app/agents/foundation/ tests/unit/test_foundation_llm.py
git commit -m "feat: port resilient LLM foundation (FallbackModel + run metadata)"
```

---

### Task 4: Reconciliar model/schema de Client (billing fields)

**Files:**
- Modify: `app/models/client.py`
- Modify: `app/schemas/client.py:106-112` (`ClientCreate`) e `:246-262` (`from_orm`)
- Modify: `app/services/client_service.py:76-90` (`create_client`)
- Create: `migrations/versions/0002_client_billing_fields.py`
- Test: `tests/unit/test_client_schema_billing.py`

**Interfaces:**
- Produces: `Client.invoice_day: int`, `Client.consult_price: Numeric`. `ClientCreate` passa a exigir `invoice_day: int` e `consult_price: Decimal`. `ClientResponse.from_orm` deixa de quebrar.
- Consumes: `ClientService.create_client(ClientCreate) -> ClientResponse` (já existe).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_client_schema_billing.py
from decimal import Decimal
from uuid import uuid4
from app.schemas.client import ClientCreate

def test_client_create_requires_billing_fields():
    c = ClientCreate(
        name="Maria Silva",
        phone="+5551981321543",
        user_id=uuid4(),
        invoice_day=10,
        consult_price=Decimal("200.00"),
    )
    assert c.invoice_day == 10
    assert c.consult_price == Decimal("200.00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_client_schema_billing.py -v`
Expected: FAIL — `ClientCreate` não aceita `invoice_day`/`consult_price` (TypeError/ValidationError de campo extra ou ausência dos atributos).

- [ ] **Step 3: Add columns, schema fields, persistence, migration**

In `app/models/client.py`, add to imports `Numeric, Integer` from sqlalchemy, and add columns after `notes`:

```python
    invoice_day = Column(Integer, nullable=True)
    consult_price = Column(Numeric(10, 2), nullable=True)
```

In `app/schemas/client.py`, add to `ClientCreate` (after `user_id`):

```python
    invoice_day: int = Field(..., ge=1, le=31, description="Dia do mês para faturamento")
    consult_price: Decimal = Field(..., ge=0, description="Preço da consulta em reais")
```

In `client_service.create_client`, include the fields when building `Client(...)`:

```python
                invoice_day=client_data.invoice_day,
                consult_price=client_data.consult_price,
```

`ClientResponse.from_orm` already references `client.invoice_day`/`client.consult_price` — now valid.

Create `migrations/versions/0002_client_billing_fields.py`:

```python
"""add client billing fields

Revision ID: 0002_client_billing_fields
Revises: 0001_initial_migration
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_client_billing_fields"
down_revision = "0001_initial_migration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("invoice_day", sa.Integer(), nullable=True), schema="simplificapsi")
    op.add_column("clients", sa.Column("consult_price", sa.Numeric(10, 2), nullable=True), schema="simplificapsi")


def downgrade() -> None:
    op.drop_column("clients", "consult_price", schema="simplificapsi")
    op.drop_column("clients", "invoice_day", schema="simplificapsi")
```

Confirme o `down_revision` real com `head` atual: `alembic heads` (ajuste o id se o `0001` tiver outro slug).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_client_schema_billing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/client.py app/schemas/client.py app/services/client_service.py migrations/versions/0002_client_billing_fields.py tests/unit/test_client_schema_billing.py
git commit -m "feat: add invoice_day and consult_price to Client model/schema"
```

---

### Task 5: `AgentDeps` — contexto tipado do agente

**Files:**
- Create: `app/agents/deps.py`
- Test: `tests/unit/test_agent_deps.py`

**Interfaces:**
- Produces: `AgentDeps` (pydantic dataclass) com campos:
  - `db: Session`
  - `user_id: UUID`
  - `user_name: str | None`
  - `current_datetime: datetime`
  - `timezone: str`
  - `history_summary: str | None`
  - `client_service: ClientService`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_agent_deps.py
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock
from app.agents.deps import AgentDeps

def test_agent_deps_holds_context():
    deps = AgentDeps(
        db=MagicMock(),
        user_id=uuid4(),
        user_name="Ramon",
        current_datetime=datetime(2026, 6, 21, 15, 0),
        timezone="America/Sao_Paulo",
        history_summary=None,
        client_service=MagicMock(),
    )
    assert deps.user_name == "Ramon"
    assert deps.timezone == "America/Sao_Paulo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_deps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.deps'`

- [ ] **Step 3: Implement**

```python
# app/agents/deps.py
"""Typed dependencies injected into the SimplificaAgent run."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.client_service import ClientService


@dataclass
class AgentDeps:
    db: Session
    user_id: UUID
    user_name: Optional[str]
    current_datetime: datetime
    timezone: str
    history_summary: Optional[str]
    client_service: ClientService
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_deps.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/deps.py tests/unit/test_agent_deps.py
git commit -m "feat: add typed AgentDeps for agent context"
```

---

### Task 6: Tools de cliente (impl puras + wrappers)

**Files:**
- Create: `app/agents/tools/__init__.py`
- Create: `app/agents/tools/client_tools.py`
- Test: `tests/unit/test_client_tools.py`

**Interfaces:**
- Consumes: `AgentDeps` (Task 5), `ClientService`, schemas `ClientCreate`/`ClientUpdate`.
- Produces (funções-impl puras, testáveis sem LLM; todas retornam `dict` `{success,data,message}`):
  - `async def create_client_impl(deps: AgentDeps, name: str, phone: str, invoice_day: int, consult_price: float, email: str | None = None) -> dict`
  - `async def find_client_impl(deps: AgentDeps, name: str | None = None, phone: str | None = None) -> dict`
  - `async def list_clients_impl(deps: AgentDeps, active_only: bool = True) -> dict`
  - `async def update_client_impl(deps: AgentDeps, phone: str, **fields) -> dict`
  - `async def deactivate_client_impl(deps: AgentDeps, phone: str, reason: str) -> dict`
  - `def register_client_tools(agent) -> None` — registra os wrappers `@agent.tool` que chamam as impl com `ctx.deps`.

Nota de design: a `message` nunca inclui IDs. `data` pode conter campos de negócio (nome, telefone) mas o agente é instruído (Task 7) a não vazar IDs.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_client_tools.py
import pytest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.agents.tools.client_tools import (
    create_client_impl,
    find_client_impl,
)

def _deps_with_service(service):
    return SimpleNamespace(
        db=MagicMock(), user_id=uuid4(), user_name="Ramon",
        current_datetime=None, timezone="America/Sao_Paulo",
        history_summary=None, client_service=service,
    )

@pytest.mark.asyncio
async def test_create_client_impl_success():
    service = MagicMock()
    created = SimpleNamespace(name="Maria Silva", phone="+5551981321543")
    service.create_client = AsyncMock(return_value=created)
    deps = _deps_with_service(service)

    result = await create_client_impl(
        deps, name="Maria Silva", phone="+5551981321543",
        invoice_day=10, consult_price=200.0,
    )

    assert result["success"] is True
    assert "Maria" in result["message"]
    service.create_client.assert_awaited_once()

@pytest.mark.asyncio
async def test_find_client_impl_not_found_returns_actionable_message():
    service = MagicMock()
    service.find_client_by_phone = AsyncMock(return_value=None)
    service.find_client_by_name = AsyncMock(return_value=[])
    deps = _deps_with_service(service)

    result = await find_client_impl(deps, name="Carlos Souza")

    assert result["success"] is False
    assert "Carlos" in result["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_client_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.tools.client_tools'`

- [ ] **Step 3: Implement**

```python
# app/agents/tools/__init__.py
"""Agent tools."""
```

```python
# app/agents/tools/client_tools.py
"""Client management tools: pure impls + thin @agent.tool wrappers."""

from decimal import Decimal
from typing import Optional

from app.agents.deps import AgentDeps
from app.core.exceptions import ConflictError, ValidationError
from app.schemas.client import ClientCreate, ClientUpdate


async def create_client_impl(
    deps: AgentDeps,
    name: str,
    phone: str,
    invoice_day: int,
    consult_price: float,
    email: Optional[str] = None,
) -> dict:
    try:
        payload = ClientCreate(
            name=name, phone=phone, email=email, user_id=deps.user_id,
            invoice_day=invoice_day, consult_price=Decimal(str(consult_price)),
        )
    except Exception as e:  # pydantic ValidationError (phone/name rules)
        return {"success": False, "data": None, "message": f"Dados inválidos: {e}"}

    try:
        client = await deps.client_service.create_client(payload)
    except ConflictError as e:
        return {"success": False, "data": None, "message": str(e)}
    except ValidationError as e:
        return {"success": False, "data": None, "message": str(e)}

    first_name = client.name.split()[0]
    return {
        "success": True,
        "data": {"name": client.name, "phone": client.phone},
        "message": f"Cliente {first_name} cadastrado com sucesso.",
    }


async def find_client_impl(
    deps: AgentDeps,
    name: Optional[str] = None,
    phone: Optional[str] = None,
) -> dict:
    if phone:
        client = await deps.client_service.find_client_by_phone(phone, deps.user_id)
        if client:
            return {"success": True, "data": {"name": client.name, "phone": client.phone},
                    "message": f"Encontrei {client.name.split()[0]}."}
        return {"success": False, "data": None,
                "message": f"Não encontrei cliente com o telefone {phone}."}

    if name:
        matches = await deps.client_service.find_client_by_name(name, deps.user_id)
        if len(matches) == 1:
            c = matches[0]
            return {"success": True, "data": {"name": c.name, "phone": c.phone},
                    "message": f"Encontrei {c.name.split()[0]}."}
        if len(matches) > 1:
            names = ", ".join(m.name for m in matches)
            return {"success": False, "data": {"candidates": names},
                    "message": f"Encontrei vários clientes para '{name}': {names}. "
                               f"Pode informar o telefone para identificar?"}
        first = name.split()[0]
        return {"success": False, "data": None,
                "message": f"Não encontrei cliente chamado {first}. Quer cadastrar?"}

    return {"success": False, "data": None,
            "message": "Preciso do nome ou telefone do cliente para buscar."}


async def list_clients_impl(deps: AgentDeps, active_only: bool = True) -> dict:
    page = await deps.client_service.list_clients(
        deps.user_id, is_active=True if active_only else None, page=1, per_page=100
    )
    names = [c.name for c in page.clients]
    return {"success": True, "data": {"names": names, "total": page.total},
            "message": f"Você tem {page.total} cliente(s)."}


async def update_client_impl(deps: AgentDeps, phone: str, **fields) -> dict:
    client = await deps.client_service.find_client_by_phone(phone, deps.user_id)
    if not client:
        return {"success": False, "data": None,
                "message": f"Não encontrei cliente com o telefone {phone}."}
    try:
        payload = ClientUpdate(**fields)
        updated = await deps.client_service.update_client(client.id, deps.user_id, payload)
    except (ConflictError, ValidationError) as e:
        return {"success": False, "data": None, "message": str(e)}
    except Exception as e:
        return {"success": False, "data": None, "message": f"Dados inválidos: {e}"}
    return {"success": True, "data": {"name": updated.name, "phone": updated.phone},
            "message": f"Dados de {updated.name.split()[0]} atualizados."}


async def deactivate_client_impl(deps: AgentDeps, phone: str, reason: str) -> dict:
    client = await deps.client_service.find_client_by_phone(phone, deps.user_id)
    if not client:
        return {"success": False, "data": None,
                "message": f"Não encontrei cliente com o telefone {phone}."}
    await deps.client_service.deactivate_client(client.id, deps.user_id)
    return {"success": True, "data": {"name": client.name},
            "message": f"{client.name.split()[0]} foi desativado(a)."}


def register_client_tools(agent) -> None:
    """Register thin @agent.tool wrappers that delegate to the pure impls."""
    from pydantic_ai import RunContext

    @agent.tool
    async def create_client(
        ctx: RunContext[AgentDeps], name: str, phone: str,
        invoice_day: int, consult_price: float, email: Optional[str] = None,
    ) -> dict:
        """Cadastra um novo cliente (nome+sobrenome, telefone, dia de cobrança, preço da consulta)."""
        return await create_client_impl(ctx.deps, name, phone, invoice_day, consult_price, email)

    @agent.tool
    async def find_client(
        ctx: RunContext[AgentDeps], name: Optional[str] = None, phone: Optional[str] = None,
    ) -> dict:
        """Busca um cliente por nome ou telefone."""
        return await find_client_impl(ctx.deps, name, phone)

    @agent.tool
    async def list_clients(ctx: RunContext[AgentDeps], active_only: bool = True) -> dict:
        """Lista os clientes do psicólogo."""
        return await list_clients_impl(ctx.deps, active_only)

    @agent.tool
    async def update_client(ctx: RunContext[AgentDeps], phone: str, **fields) -> dict:
        """Atualiza dados de um cliente identificado pelo telefone."""
        return await update_client_impl(ctx.deps, phone, **fields)

    @agent.tool
    async def deactivate_client(ctx: RunContext[AgentDeps], phone: str, reason: str) -> dict:
        """Desativa um cliente (soft delete) com um motivo."""
        return await deactivate_client_impl(ctx.deps, phone, reason)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_client_tools.py -v`
Expected: PASS (2 passed). Requer `pytest-asyncio`; se faltar, `uv add --dev pytest-asyncio` e garanta `asyncio_mode = "auto"` no `pyproject.toml`/`pytest.ini`.

- [ ] **Step 5: Commit**

```bash
git add app/agents/tools/ tests/unit/test_client_tools.py
git commit -m "feat: add client management tools (pure impls + agent wrappers)"
```

---

### Task 7: `SimplificaAgent` — montagem + system prompt

**Files:**
- Create: `app/agents/simplifica_agent.py`
- Test: `tests/unit/test_simplifica_agent.py`

**Interfaces:**
- Consumes: `get_llm_model` (Task 3), `AgentDeps` (Task 5), `register_client_tools` (Task 6), `settings.SIMPLIFICA_AGENT_MODEL`.
- Produces:
  - `build_simplifica_agent() -> Agent[AgentDeps, str]` — agente com `deps_type=AgentDeps`, `output_type=str`, tools de cliente registradas, system prompt estático + dinâmico (injeta data/usuário/timezone/resumo).
  - `SIMPLIFICA_SYSTEM_PROMPT: str` (constante).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_simplifica_agent.py
import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart

from app.agents.simplifica_agent import build_simplifica_agent
from app.agents.deps import AgentDeps

models.ALLOW_MODEL_REQUESTS = False  # guard: no real network

@pytest.mark.asyncio
async def test_agent_calls_create_client_tool_then_replies():
    # Script: first model turn calls create_client; second turn returns text.
    calls = {"n": 0}

    async def scripted(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(parts=[ToolCallPart(
                tool_name="create_client",
                args={"name": "Maria Silva", "phone": "+5551981321543",
                      "invoice_day": 10, "consult_price": 200.0},
            )])
        return ModelResponse(parts=[TextPart("Pronto! Cliente cadastrado. ✅")])

    agent = build_simplifica_agent()

    service = MagicMock()
    created = SimpleNamespace(name="Maria Silva", phone="+5551981321543")
    service.create_client = AsyncMock(return_value=created)
    deps = AgentDeps(
        db=MagicMock(), user_id=uuid4(), user_name="Ramon",
        current_datetime=datetime(2026, 6, 21, 15, 0),
        timezone="America/Sao_Paulo", history_summary=None, client_service=service,
    )

    with agent.override(model=FunctionModel(scripted)):
        result = await agent.run("cadastra a Maria Silva, 51 98132-1543, dia 10, 200 reais", deps=deps)

    assert "cadastrado" in result.output.lower()
    service.create_client.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_simplifica_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.simplifica_agent'`

- [ ] **Step 3: Implement**

```python
# app/agents/simplifica_agent.py
"""SimplificaAgent: single tool-calling agent for practice management."""

from pydantic_ai import Agent, RunContext

from app.agents.deps import AgentDeps
from app.agents.foundation import get_llm_model
from app.agents.tools.client_tools import register_client_tools
from app.core.config import settings

SIMPLIFICA_SYSTEM_PROMPT = """Você é o assistente pessoal do Simplifica Psi para psicólogos e terapeutas.

CONTEXTO:
- O usuário é o PROFISSIONAL (psicólogo/terapeuta), nunca o paciente.
- Você ajuda a gerenciar a prática pessoal dele: cadastro de clientes, agenda e cobrança.
- Fale de "seus clientes", "sua agenda", "seu consultório". Nunca "clínica".

REGRAS DE RESPOSTA:
- Responda sempre em Português do Brasil, tom de assistente pessoal, direto e amigável.
- NUNCA exponha IDs, códigos, JSON, metadados, HTML, markdown ou URLs.
- Em sucesso: confirme de forma positiva. Em falha: seja proativo, peça exatamente o que falta
  ou ajude a refinar (ex.: vários homônimos -> peça o telefone).
- Use as tools para qualquer ação ou consulta de dados. Nunca invente dados.
- Para cadastrar cliente são necessários: nome e sobrenome, telefone, dia de cobrança e preço da consulta.
"""


def build_simplifica_agent() -> Agent:
    agent = Agent(
        get_llm_model(settings.SIMPLIFICA_AGENT_MODEL, temperature=0.1, timeout=30),
        deps_type=AgentDeps,
        output_type=str,
        system_prompt=SIMPLIFICA_SYSTEM_PROMPT,
        retries=3,
    )

    @agent.system_prompt
    def add_runtime_context(ctx: RunContext[AgentDeps]) -> str:
        d = ctx.deps
        when = d.current_datetime.strftime("%d/%m/%Y %H:%M") if d.current_datetime else "agora"
        lines = [
            f"Usuário: {d.user_name or 'profissional'}",
            f"Data/hora atual: {when} ({d.timezone})",
        ]
        if d.history_summary:
            lines.append(f"Resumo da conversa até aqui: {d.history_summary}")
        return "\n".join(lines)

    register_client_tools(agent)
    return agent
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_simplifica_agent.py -v`
Expected: PASS. Se a assinatura do `FunctionModel`/`ModelResponse` divergir da versão instalada do Pydantic AI, ajuste os imports conforme `python -c "import pydantic_ai; print(pydantic_ai.__version__)"` e a doc da versão (o conceito — scriptar tool call + texto — permanece).

- [ ] **Step 5: Commit**

```bash
git add app/agents/simplifica_agent.py tests/unit/test_simplifica_agent.py
git commit -m "feat: assemble SimplificaAgent with system prompt and client tools"
```

---

### Task 8: Endpoint HTTP — `POST {API_PREFIX}/agent/message`

**Files:**
- Create: `app/api/agent_routes.py`
- Modify: `app/main.py` (registrar o router)
- Test: `tests/integration/test_agent_message_endpoint.py`

**Interfaces:**
- Consumes: `build_simplifica_agent` (Task 7), `AgentDeps` (Task 5), `ClientService`, `get_db` (sessão DB — confirmar nome em `app/core/database.py`).
- Produces: `POST {settings.API_PREFIX}/agent/message` com body `{"user_id": "<uuid>", "message": "<str>"}` → `{"content": "<str>"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_agent_message_endpoint.py
import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart

from app.main import app
from app.api import agent_routes
from app.core.config import settings

models.ALLOW_MODEL_REQUESTS = False

def test_agent_message_returns_content(monkeypatch):
    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("Olá! Como posso ajudar com seus clientes?")])

    # Force the agent to use the scripted model and a mock client service.
    real_build = agent_routes.build_simplifica_agent
    def build_with_override():
        ag = real_build()
        ag._test_model_cm = ag.override(model=FunctionModel(scripted))
        ag._test_model_cm.__enter__()
        return ag
    monkeypatch.setattr(agent_routes, "build_simplifica_agent", build_with_override)
    monkeypatch.setattr(agent_routes, "ClientService", lambda db: MagicMock())

    client = TestClient(app)
    resp = client.post(f"{settings.API_PREFIX}/agent/message",
                       json={"user_id": str(uuid4()), "message": "oi"})
    assert resp.status_code == 200
    assert "content" in resp.json()
    assert resp.json()["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_agent_message_endpoint.py -v`
Expected: FAIL — rota inexistente (404) ou `ImportError` de `app.api.agent_routes`.

- [ ] **Step 3: Implement**

Confirme o nome da dependência de sessão: `grep -n "def get_db\|def get_session" app/core/database.py`. Use o nome real no lugar de `get_db` abaixo.

```python
# app/api/agent_routes.py
"""HTTP entrypoint for the SimplificaAgent."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.deps import AgentDeps
from app.agents.simplifica_agent import build_simplifica_agent
from app.core.config import settings
from app.core.database import get_db
from app.services.client_service import ClientService

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentMessageRequest(BaseModel):
    user_id: UUID
    message: str


class AgentMessageResponse(BaseModel):
    content: str


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest, db: Session = Depends(get_db)):
    agent = build_simplifica_agent()
    deps = AgentDeps(
        db=db,
        user_id=payload.user_id,
        user_name=None,
        current_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
        timezone=settings.TIMEZONE,
        history_summary=None,
        client_service=ClientService(db),
    )
    result = await agent.run(payload.message, deps=deps)
    return AgentMessageResponse(content=result.output)
```

In `app/main.py`, register the router (follow the existing pattern for other routers):

```python
from app.api.agent_routes import router as agent_router
app.include_router(agent_router, prefix=settings.API_PREFIX)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_agent_message_endpoint.py -v`
Expected: PASS. Se `get_db` exigir um banco real, sobreponha via `app.dependency_overrides[get_db]` no teste retornando um `MagicMock()` de sessão.

- [ ] **Step 5: Commit**

```bash
git add app/api/agent_routes.py app/main.py tests/integration/test_agent_message_endpoint.py
git commit -m "feat: add POST /agent/message endpoint wiring SimplificaAgent"
```

---

### Task 9: Suíte verde + push

**Files:** nenhum novo.

- [ ] **Step 1: Rodar a suíte inteira**

Run: `pytest -q`
Expected: todos os testes deste plano passam. Falhas em testes legados (se houver) devem ter sido removidas na Task 1; investigue qualquer remanescente.

- [ ] **Step 2: Push**

```bash
git push origin main
```

Expected: push aceito (remote `main` atualizado).

---

## Roadmap — próximos planos (cada um com seu próprio spec→plano→execução)

- **Plano 2 — Agenda (Google Calendar):** `google_calendar_service` (OAuth por-usuário + SDK oficial `google-api-python-client`), `calculate_date_range`, tools `create_event`/`create_recurring_event`/`list_events`/`update_event`/`cancel_event`, persistência de `google_event_id` no Postgres, regra "evento exige cliente existente".
- **Plano 3 — Cobrança:** tools `mark_paid`/`list_pending_payments`/`send_payment_reminder`, integração simple-charge/Evolution.
- **Plano 4 — Memória de sessão + WhatsApp:** persistência de `ChatSession`/`Message`, resumo contínuo barato (N=10/X=6), debounce Redis, webhook Evolution API.
- **Plano 5 — Eval & escolha de modelo:** eval-set (~20 conversas), métricas de tool-calling/qualidade/custo/latência, fixar primário/fallback.
- **Plano 6 — Fiscal (Receita Saúde):** tools `issue_receipt`/`issue_invoice`.

---

## Self-Review notes

- **Cobertura do spec (fatia deste plano):** fundação LLM (Tasks 2-3) ✓; agente único + tools de cliente (Tasks 5-7) ✓; guard-rails no código — telefone via schema, nome+sobrenome, soft-delete, sem IDs na message (Tasks 4, 6, 7) ✓; endpoint (Task 8) ✓. Agenda/cobrança/memória/eval/fiscal → roadmap (fora deste plano, por decomposição).
- **Divergência tratada:** model `Client` sem `invoice_day`/`consult_price` (bug existente) corrigido na Task 4 antes de qualquer tool depender disso.
- **Risco de versão do Pydantic AI:** Tasks 7-8 dependem de `FunctionModel`/`ModelResponse`/`agent.override`. Os passos instruem verificar a versão instalada e ajustar imports se a API divergir, mantendo a estratégia de teste.
