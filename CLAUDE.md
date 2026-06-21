# CLAUDE.md — chatbot-scheduler (SimplificaPsi Agent)

Guia de desenvolvimento deste repositório. Leia antes de codar.

---

## 1. O que é

Sistema de **agentes de IA** que opera o **Simplifica Psi** — assistente de gestão de consultório para **psicólogos e terapeutas**, via conversa em linguagem natural (PT-BR), tipicamente no WhatsApp.

- O usuário é sempre o **profissional** (psicólogo/terapeuta), **nunca o paciente**.
- Domínios: **clientes** (cadastro), **agenda** (Google Calendar), **cobrança** (pagamentos/lembretes) e, por último, **fiscal** (Receita Saúde).
- Linguagem ao usuário: "seu consultório / seus clientes / sua agenda". **Nunca** "clínica".

Visão completa do produto/domínio: `../simplifica-psi-chatbot/PROJECT_OVERVIEW.md` (análise do sistema legado TS).

> **Greenfield:** este repo nasceu do antigo `python-simplifica-psi`, mas o esqueleto de agentes anterior era mockado/quebrado e está sendo **reconstruído do zero** conforme o design abaixo. Não trate o código legado como autoridade — o spec e o plano são a fonte da verdade.

---

## 2. Decisões de arquitetura (já fechadas)

1. **Agente único com tools** (`SimplificaAgent`), não manager+especialistas. Uma chamada de raciocínio por mensagem; o LLM orquestra via tool-calling nativo. Sem intent-parser/manager/formatter separados (erros do legado).
2. **Google Calendar = fonte da verdade** da agenda. Postgres guarda só o dado de negócio (cliente, pagamento) ligado por `google_event_id`. **Sem sync bidirecional.**
3. **Não usar MCP de Google** — usar o SDK oficial (`google-api-python-client`) atrás de um wrapper fino. Motivo: auth multi-tenant por-usuário, guard-rails de negócio na tool, dual-write Postgres, superfície de tools enxuta.
4. **Fundação de LLM portada do `rooster-platform`** (do Bruno): `get_llm_model()` retorna um `FallbackModel` (cadeia OpenAI→OpenRouter→menor) — resiliência de provedor de graça. Ver `app/agents/foundation/llm.py`.
5. **Escolha do modelo principal é por eval**, não por achismo (candidatos: `claude-haiku-4.5`, `gpt-5.4-mini`).
6. **Ingestão de mensagens é provider-agnostic** (Plano 4): uma porta única (`InboundMessage`) com adapters que normalizam **Evolution API** e **WhatsApp Oficial (Meta Cloud API)** para um formato interno comum. O agente nunca conhece o provedor de origem; trocar/adicionar provedor é só um adapter novo. O mesmo vale para o envio (porta de saída).

Spec: `docs/superpowers/specs/2026-06-21-simplifica-agent-system-design.md`
Plano atual: `docs/superpowers/plans/2026-06-21-foundation-and-clients-slice.md`

---

## 3. Stack

Python 3.11+ · **Pydantic AI** (`pydantic-ai-slim[openai]` ≥1.41) · Pydantic v2 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL · Redis · Google Calendar API · uv (gerenciador) · pytest.

LLM via OpenAI direto + OpenRouter (fallback). Chaves em `.env`: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`.

---

## 4. Estrutura

```
app/
  agents/
    foundation/      # get_llm_model (FallbackModel) + get_llm_run_metadata  [portado do rooster]
    deps.py          # AgentDeps — contexto tipado injetado no agente
    simplifica_agent.py   # build_simplifica_agent() + system prompt
    tools/           # client_tools.py, (futuro) calendar_tools, billing_tools
  api/               # rotas FastAPI (agent_routes.py)
  core/              # config.py, database.py (get_db), logging, redis, exceptions
  models/            # SQLAlchemy: user, client, event, calendar, chat_session
  schemas/           # Pydantic I/O (client.py com validação de telefone via phonenumbers)
  services/          # client_service.py (CRUD), (futuro) calendar/billing services
migrations/          # Alembic
scripts/             # init-db.sql, seed_dev.py
tests/               # unit/ e integration/
docs/superpowers/    # specs/ e plans/
```

---

## 5. Convenções (obrigatórias)

- **Código/identificadores/enums em inglês.** Mensagens ao usuário final em **PT-BR**.
- **Models no schema Postgres `simplificapsi`** (`__table_args__ = {"schema": "simplificapsi"}`).
- **Contrato de tool:** toda tool retorna `dict` `{"success": bool, "data": Any, "message": str}`. A `message` **nunca** contém IDs/JSON/HTML/markdown/URLs.
- **Guard-rails de negócio vivem no código** (tools/services/schemas), não confiados ao LLM: validação de telefone, "evento exige cliente existente", soft-delete com motivo, nunca vazar IDs.
- **Padrão de tool:** função-impl pura (`*_impl`, testável sem LLM) + wrapper fino `@agent.tool` que chama a impl com `ctx.deps`.
- **TDD:** comportamento novo começa por um teste que falha (red→green). Commits pequenos e frequentes, um por task do plano.
- **Timezone fixo:** `America/Sao_Paulo`. Semana começa no domingo.
- **Telefone:** validado via `phonenumbers` (região default `BR`).
- **Sem segredos no git** (`.env`, `credentials.json`, `token.json` já no `.gitignore`).
- **Commits/PRs nunca atribuem a IA** (sem "Co-Authored-By: Claude" etc.).

---

## 6. Fluxo de desenvolvimento (comandos)

Setup inicial:

```bash
make setup          # uv sync (cria .venv) + pre-commit
cp env.example .env # preencher OPENAI_API_KEY, OPENROUTER_API_KEY, DATABASE_URL, SECRET_KEY, JWT_SECRET_KEY
```

Dois modos de rodar a infra:

**A) Tudo no Docker (mais simples):**
```bash
make dev            # sobe postgres + redis + app + pgadmin + redis-commander
make logs           # acompanha logs do app
make stop
```

**B) Infra no Docker, app local (melhor para debugar o agente):**
```bash
make infra          # sobe APENAS postgres + redis
make migrate        # aplica migrações Alembic (local, contra a infra)
make seed           # garante o usuário de dev (UUID abaixo)
make run            # uvicorn local com reload em http://localhost:8000
```

Testar rápido o agente (sem WhatsApp): o endpoint `POST /api/v1/agent/message`:
```bash
make chat MSG="cadastra a Maria Silva, 51 98132-1543, dia 10, 200 reais"
```

Qualidade e testes:
```bash
make test           # pytest (unit + integration)
make test-unit
make lint           # ruff check + mypy
make format         # ruff format + ruff check --fix
```

Banco:
```bash
make psql           # shell psql na infra
make redis          # redis-cli
make migration MESSAGE="add x"   # cria migração autogenerate
```

**Usuário de dev fixo** (semeado por `scripts/init-db.sql` e por `make seed`):
`550e8400-e29b-41d4-a716-446655440000` — use esse `user_id` ao chamar o endpoint.

---

## 7. Pontos de atenção / dívidas conhecidas

- **Schema = Alembic (fonte única).** `scripts/init-db.sql` só prepara extensões + schema `simplificapsi` + grants; **tabelas/índices vêm das migrações** (`make migrate`) e o usuário de dev vem do `make seed`. Não recriar tabelas no `init-db.sql`.
- **Legado mockado** (`workflow.py`, `agent_manager.py`, `calendar_agent.py`, `client_agent.py`) está marcado para remoção no Plano 1, Task 1.
- **`phonenumbers` travado em `BR`** — multi-país é deferido.
- **Regra herdada:** nome de cliente exige nome+sobrenome (≥2 palavras). Pode conflitar com uso conversacional ("cadastra a Maria"); revisitar se atrapalhar.

---

## 8. Para agentes/IA trabalhando aqui

- Leia este arquivo + o spec + o plano antes de codar.
- Siga o plano task-by-task (skill `superpowers:subagent-driven-development` ou `executing-plans`).
- Não reintroduza camadas do legado (intent-parser/manager/formatter).
- Não invente IDs de modelo LLM: use os nomes do catálogo em `app/agents/foundation/llm.py`.
