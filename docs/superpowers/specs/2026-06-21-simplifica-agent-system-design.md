# SimplificaPsi — Sistema de Agentes (v1) — Design

**Data:** 2026-06-21
**Status:** Aprovado (design) — pronto para plano de implementação
**Stack:** Python 3.11+ · Pydantic AI · FastAPI · PostgreSQL · Redis · Google Calendar API

---

## 1. Objetivo e visão

Construir, do zero, o sistema de agentes de IA que opera o **Simplifica Psi** — assistente de gestão de consultório para **psicólogos e terapeutas**, via conversa em linguagem natural (PT-BR), tipicamente no WhatsApp.

O usuário é sempre o **profissional** (nunca o paciente). O assistente gerencia a **prática pessoal** do profissional: agenda, cadastro de clientes, cobrança e (fase final) emissão fiscal. Linguagem de "seu consultório / seus clientes / sua agenda", nunca "clínica".

### Princípios de design

- **Simplicidade primeiro:** 1 agente, 1 chamada de raciocínio por mensagem. Sem intent-parser, sem manager, sem formatter separado (erros do legado TS que geravam 4-5 chamadas de LLM e fragilidade).
- **Regra de negócio no código, não no prompt:** validações determinísticas vivem nas tools/services; o LLM orquestra, não valida criticamente.
- **Fonte da verdade única por domínio:** Google Calendar para agendamento; Postgres para dado de negócio. Sem sync bidirecional.
- **Resiliência de provedor de graça:** todo modelo é uma cadeia de fallback.
- **Decisões de modelo por evidência (eval), não por achismo.**

---

## 2. Arquitetura geral

Um único agente Pydantic AI — `SimplificaAgent` — com todas as tools. O LLM orquestra via tool-calling nativo.

```
WhatsApp (Evolution API webhook)
  → debounce (Redis: agrega mensagens picadas em ~2-3s)
  → carrega contexto (deps): user, data/hora, timezone, histórico recente + resumo da sessão
  → SimplificaAgent.run()            ← UMA chamada de raciocínio
       ├─ tools de cliente   → client_service (Postgres)
       ├─ tools de agenda    → Google Calendar API (fonte da verdade)
       ├─ tools de cobrança  → Postgres + simple-charge / Zap Pay (Evolution)
       └─ tools fiscais (v2) → Receita Saúde
  → resposta natural em PT-BR (o próprio agente formata)
  → persiste mensagem user + assistant na sessão
```

**Contraste com o legado:** o `simplifica-psi-chatbot` (TS) fazia `intent-parser → manager → sub-agente → loop → formatter`. Aqui, uma única passagem do agente substitui toda essa cadeia. As regras de tom/formatação que viviam em `prompts.ts` passam para o `system_prompt` do agente.

---

## 3. Fundação reaproveitada do `rooster-platform` (Bruno)

Copiar/portar para `app/agents/_foundation/` (ou `shared/`):

- **`get_llm_model(model_name, temperature, timeout) -> FallbackModel`** (`shared/utils/llm.py`):
  cada modelo lógico é uma cadeia OpenAI-direto → OpenRouter → modelo menor. Resiliência a queda/timeout de provedor sem código extra. Já traz `seed=0`, `temperature`, `timeout`. Catálogo inclui `gpt-5.4-mini`, `gpt-5-mini`, `gpt-5.4-nano`, `claude-haiku-4.5`, `claude-sonnet-4.6`, `gemini-3.1-flash-lite` etc.
- **Padrão de agente** (`shared/agents/competition_finder.py`): classe fina envolvendo `pydantic_ai.Agent`, com `system_prompt` estático + `@agent.system_prompt` dinâmico (injeta `deps`), `deps_type` tipado e `retries`.
- **`get_llm_run_metadata(result)`** (`shared/utils/llm.py`): extrai tokens (input/reasoning/output), modelo e provider por chamada → observabilidade de custo desde o dia 1.

**Nota sobre output:** ao contrário do `competition_finder` (que usa `output_type` estruturado), a resposta final do `SimplificaAgent` ao usuário é **texto livre** (conversa). O I/O tipado fica nas **tools** (entrada/saída Pydantic) e em tarefas auxiliares (ex.: resolver data relativa).

---

## 4. Componentes (unidades isoladas)

| Unidade | Responsabilidade | Depende de |
|---|---|---|
| `SimplificaAgent` | Orquestra a conversa e o tool-calling; formata a resposta PT-BR | foundation LLM, tools, deps |
| `AgentDeps` | Contexto tipado por mensagem (user, data/hora, timezone, resumo, histórico) | models de sessão |
| `client_tools` | CRUD/desativação de clientes | `client_service` (Postgres) |
| `calendar_tools` | Eventos no Google Calendar (criar/listar/atualizar/cancelar/recorrente) | `google_calendar_service`, `calculate_date_range` |
| `billing_tools` | Marcar pago, listar pendências, lembrete de cobrança | Postgres, `simple-charge`/Evolution |
| `fiscal_tools` (fase final) | Recibo e nota fiscal | Receita Saúde |
| `google_calendar_service` | Wrapper da API do GCal (auth OAuth + chamadas) | `google-auth-library`, `googleapis` |
| `calculate_date_range` | Resolve datas relativas ("hoje", "semana que vem", "mês que vem") no servidor | date utils, locale pt-BR |
| `session_memory` | Carrega histórico + resumo; atualiza resumo de forma barata | models `ChatSession`/`Message` |
| `message_debouncer` | Agrega mensagens picadas (Redis) | Redis |
| `whatsapp_webhook` | Entrada Evolution API → pipeline | FastAPI, debouncer |

Cada unidade tem propósito único, interface clara e é testável isoladamente.

---

## 5. Tools — contratos

Toda tool retorna `dict` tipado `{ "success": bool, "data": ..., "message": str }`. A `message` **nunca** contém IDs/JSON; o agente decide a resposta ao usuário a partir do retorno.

### 5.1 Cliente (`client_tools`)
- `create_client(name, phone, invoice_day, consult_price, email?)`
- `find_client(name? | phone? | id?)`
- `list_clients(active_only=True)`
- `update_client(client_ref, **fields)`
- `deactivate_client(client_ref, reason)`

### 5.2 Agenda — Google Calendar fonte da verdade (`calendar_tools`)
- `create_event(client_ref, start_time, duration?, title?)`
- `create_recurring_event(client_ref, start_time, frequency, weekdays?, until?)`
- `list_events(period)` — `period` resolvido por `calculate_date_range`
- `update_event(event_ref, **changes)`
- `cancel_event(event_ref, reason?)`

Escrita grava `google_event_id` no Postgres quando há cliente/pagamento ligado.

### 5.3 Cobrança (`billing_tools`)
- `mark_paid(event_ref, amount?)`
- `list_pending_payments(client_ref? , period?)`
- `send_payment_reminder(client_ref, period?)` — via simple-charge/Evolution

### 5.4 Fiscal — **fase final** (`fiscal_tools`)
- `issue_receipt(event_ref | client_ref, period)`
- `issue_invoice(event_ref | client_ref, period)` — Receita Saúde

---

## 6. Regras de negócio como guard-rails (no código)

Validação **não** é confiada ao LLM — vive nas tools/services:

1. **Telefone** em formato internacional válido (regex por país: BR `+55`, US `+1`, principais da Europa) antes de gravar.
2. **Evento exige cliente existente:** `create_event`/`create_recurring_event` resolvem o cliente primeiro; se não achar → retorna `success:false` pedindo cadastro (não cria evento órfão).
3. **Soft-delete/desativação com motivo**; nunca exclusão física (`deleted_at` / `active`).
4. **Timezone fixo** `America/Sao_Paulo`; semana começa no **domingo**.
5. **Nunca expor** IDs, JSON, metadados, HTML, markdown ou URLs ao usuário (regra de prompt + tools não colocam IDs na `message`).
6. **`all_future`** limitado a ~1 ano (porta do legado).

---

## 7. Memória e contexto

Reusa os models existentes (`ChatSession`, `Message`). Por mensagem:
- Carrega últimas **N** mensagens (default **N=10**) + **resumo contínuo** da sessão → injeta em `AgentDeps`.
- Resumo atualizado de forma barata (modelo nano/mini) a cada **X** mensagens (default **X=6**) — **não** a cada uma (economia vs. legado, que resumia sempre). `N` e `X` são tunáveis por config.
- Persiste mensagem do usuário e resposta do assistente ao final de cada turno.

---

## 8. Modelos LLM — decisão por eval

Sem favorito comprometido. Usando o catálogo já wired do `rooster-platform`:

- **Agente principal (conversa + tool-calling):** candidatos `claude-haiku-4.5` e `gpt-5.4-mini` (ambos rápidos, bons em instrução e tool-calling), em `FallbackModel`. **Vencedor definido por eval.**
- **Auxiliares baratos (resumo de sessão, resolver data):** `gpt-5.4-nano` / `gemini-3.1-flash-lite`.

### Protocolo de eval
- Eval-set de ~20 conversas reais cobrindo: criar cliente, agendar evento único, agendar recorrente, listar por período, marcar pago, pedir lembrete de cobrança, casos de erro (cliente inexistente, telefone inválido, ambiguidade de homônimo).
- Métricas: **acerto de tool-calling** (tool certa + args certos), **qualidade da resposta** (tom/sem vazar IDs), **custo/tokens**, **latência**.
- Ferramenta: `pydantic-evals` ou harness próprio + `get_llm_run_metadata`.

---

## 9. Fora de escopo no v1 (consciente)

- **SimplificaBot (funil de vendas/leads):** agente *separado*, com objetivo de aquisição (ver `knowledge_base/SimplificaBot Prompt Structure.md`). A arquitetura comporta hospedá-lo depois como segundo agente; **não** se mistura ao agente de gestão.
- Sync bidirecional Postgres ↔ GCal.
- Multi-idioma; dashboard web; prontuários.

---

## 10. Fases de construção (ordem por dependência)

1. **Fundação:** portar `get_llm_model` (FallbackModel) + `get_llm_run_metadata`; esqueleto `SimplificaAgent` + `AgentDeps`; webhook + debouncer; memória de sessão.
2. **Clientes:** `client_tools` reais sobre `client_service` (substituir mocks).
3. **Agenda:** `google_calendar_service` (auth OAuth + API) + `calendar_tools` + `calculate_date_range`.
4. **Cobrança:** `billing_tools` + integração simple-charge/Evolution.
5. **Eval & escolha de modelo:** montar eval-set, rodar, fixar primário/fallback.
6. **Fiscal (final):** `fiscal_tools` + Receita Saúde.

---

## 11. Riscos e mitigações

- **Tool-calling errado em casos ambíguos** (homônimos, datas vagas) → guard-rails nas tools + eval-set cobrindo esses casos + `retries`.
- **Auth Google Calendar (OAuth/refresh token)** → isolar em `google_calendar_service`; tratar expiração e re-consentimento.
- **Crescimento do nº de tools** → se o agente único degradar (muitas tools), o design permite migrar para manager+especialistas sem reescrever as tools (elas já são isoladas).
- **Catálogo de modelos é futuro/instável** → `FallbackModel` absorve indisponibilidade; eval re-rodável quando o catálogo mudar.
