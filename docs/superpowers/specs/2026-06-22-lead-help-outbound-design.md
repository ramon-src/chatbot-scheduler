# Lead Agent + Help Tool + Minimal Outbound — Design

**Date:** 2026-06-22
**Status:** Approved (brainstorming)
**Slice of:** Plano 4 (segunda metade — agente cliente/lead + outbound), continuação da
WhatsApp Ingestion slice.
**Base branch:** `feat/lead-help-outbound` (stacked on `feat/occurrence-materialization`,
so the new migrations chain from `0010_event_occurrences`).

## Goal

Atender números **desconhecidos** (prospects de profissional) com um **agente de lead**
(vendas/onboarding) que qualifica e pode **criar a conta do profissional** num estado de
trial; dar **suporte** ao profissional já cadastrado via uma **tool de FAQ** dentro do
`SimplificaAgent`; e **enviar a resposta do lead de volta no WhatsApp** por uma porta de
outbound mínima (Evolution).

## Audiences & routing (no LLM manager)

O sistema mantém o princípio **um agente por audiência, roteado por identidade** (sem
intent-parser/manager). `IngestionService` já classifica cada inbound:

- **`professional`** (número registrado) → `SimplificaAgent` (existente). Ganha a tool
  `product_help` para suporte na mesma conversa.
- **`lead`** (número desconhecido) → `LeadAgent` (novo). Hoje os leads são parqueados;
  esta fatia liga `lead` → `dispatch_lead_run`.

Nenhuma decisão de roteamento é feita por LLM: a audiência vem do `resolve_sender`.

## Scope

**In scope:**
- `LeadAgent` (persona de vendas/onboarding) + tools de lead.
- Tool `product_help` no `SimplificaAgent` (suporte ao profissional).
- Fonte única de conhecimento de produto (PT-BR), compartilhada por lead e help.
- Tabela `leads` (fila + estado de qualificação).
- Criação de conta de profissional em **trial** (`users.access_expires_at`).
- Memória de conversa para leads, **reusando** `ChatSession`/`ChatMessage`.
- Porta de **outbound** + adapter Evolution (envio best-effort) — usada só para o lead.
- Roteamento do inbound `lead` → `dispatch_lead_run` (claim atômico, run, send).

**Out of scope (deferred):**
- **Link de pagamento / billing de ativação** ("veremos depois"). A conta é criada em
  trial; o link é apenas mencionado pelo agente, sem integração.
- **Outbound do profissional.** A resposta do `SimplificaAgent` continua persistida e
  **não** enviada no WhatsApp (como na slice de ingestão).
- **Self-serve onboarding completo** (vínculo Google Auth, calendário). A conta nasce
  utilizável para chat/cadastro; a configuração de agenda Google fica para o profissional
  depois.
- **Meta outbound.** Só Evolution send neste slice (mesma filosofia do inbound).

## Data model

### 1. `users.access_expires_at` (migration 0011)

Coluna nova `access_expires_at TIMESTAMPTZ NULL`.

- `NULL` = sem expiração (profissionais existentes / criados manualmente).
- Setada para `now() + LEAD_TRIAL_DAYS` quando o `LeadAgent` cria a conta.

Não há colunas de pagamento neste slice (YAGNI — deferido).

### 2. `leads` (migration 0012)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `phone` | varchar | normalizado; **unique** |
| `name` | varchar null | coletado na conversa |
| `email` | varchar null | coletado na conversa (necessário p/ criar conta) |
| `status` | varchar | `new` \| `engaged` \| `qualified` \| `converted` |
| `notes` | text null | observações livres do agente |
| `user_id` | UUID null | FK `simplificapsi.users.id` (setado na conversão) |
| `created_at` | timestamptz | server default now() |
| `updated_at` | timestamptz | server default now(), onupdate |

`status` default `new`. Unicidade por `phone` (um lead por número).

### 3. `chat_sessions` owner-agnostic (migration 0013)

Para **reusar** a maquinaria de memória (`ChatHistoryService`, summarizer) sem duplicar
tabelas:

- `chat_sessions.user_id` passa a ser **nullable**.
- Adiciona `lead_id UUID NULL` FK `simplificapsi.leads.id` (ondelete CASCADE).
- CHECK constraint: exatamente um owner setado
  (`(user_id IS NOT NULL) <> (lead_id IS NOT NULL)`).

`User.chat_sessions` continua válido (sessões com `user_id`); adiciona
`Lead.chat_sessions`. Migração de dados: linhas existentes já têm `user_id` → CHECK
satisfeita sem backfill.

**Alternativa considerada e descartada:** tabelas paralelas `lead_sessions`/
`lead_messages`. Rejeitada por duplicar `ChatHistoryService` + summarizer (DRY, risco de
drift).

## Components / files

| File | Responsibility |
|---|---|
| `app/models/lead.py` | modelo `Lead` |
| `app/models/user.py` | + `access_expires_at` |
| `app/models/chat_session.py` | `user_id` nullable + `lead_id` + CHECK + relationship |
| `app/agents/lead_agent.py` | `build_lead_agent()` — persona de vendas/onboarding |
| `app/agents/deps.py` | + `LeadAgentDeps` (db, lead_id, lead_name, datetime, tz, summary) |
| `app/agents/tools/lead_tools.py` | `update_lead_info`, `create_professional_account` |
| `app/agents/tools/help_tools.py` | `register_help_tools()` → tool `product_help` |
| `app/agents/knowledge/product_faq.py` | conhecimento de produto PT-BR (fonte única) |
| `app/agents/simplifica_agent.py` | registra `register_help_tools(agent)` |
| `app/channels/outbound.py` | `OutboundMessage` + `OutboundAdapter` Protocol |
| `app/channels/evolution_outbound.py` | Evolution send adapter (best-effort) |
| `app/services/lead_service.py` | `get_or_create_lead`, updates, `convert_to_account` |
| `app/services/chat_history_service.py` | + `get_or_create_lead_session(lead_id, phone)` |
| `app/services/agent_runner.py` | core genérico + `process_lead_message(...)` |
| `app/services/ingestion_service.py` | `dispatch_lead_run(inbound, record_id)` |
| `app/api/webhook_routes.py` | agenda `dispatch_lead_run` quando `status == "lead"` |
| `app/core/config.py` | + `LEAD_TRIAL_DAYS` (default 7) |
| `migrations/versions/0011_user_access_expires.py` | coluna trial |
| `migrations/versions/0012_leads.py` | tabela leads |
| `migrations/versions/0013_chat_sessions_owner.py` | owner-agnostic sessions |

### `OutboundMessage` + `OutboundAdapter` (a porta)

```python
@dataclass(frozen=True)
class OutboundMessage:
    to_phone: str   # normalized recipient
    text: str

class OutboundAdapter(Protocol):
    provider: str
    def send(self, message: OutboundMessage) -> bool: ...
    # True em envio aceito; False em falha (best-effort, nunca levanta).
```

`EvolutionOutboundAdapter.send` faz `POST {EVOLUTION_API_URL}/message/sendText/{instance}`
com header `apikey: EVOLUTION_API_KEY`. Sem credenciais configuradas → loga e retorna
`False` (não quebra o fluxo). Nunca propaga exceção.

### `LeadAgent` — persona e tools

`build_lead_agent()` espelha `build_simplifica_agent` (FallbackModel via `get_llm_model`,
`deps_type=LeadAgentDeps`, `output_type=str`, system prompt + `@agent.system_prompt`
dinâmico com data/hora, tz e resumo). Persona: assistente de vendas do Simplifica Psi,
PT-BR, acolhedor, objetivo; explica o produto, qualifica, e quando o prospect quer começar,
coleta nome + email e cria a conta em trial.

Tools (`lead_tools.py`):
- `update_lead_info(name?, email?, notes?, status?)` → atualiza o `Lead`.
- `create_professional_account(name, email)` → cria `User` (phone do lead),
  `access_expires_at = now + LEAD_TRIAL_DAYS`, marca `Lead.status="converted"` +
  `Lead.user_id`. **Idempotente**: se o phone já é um `User` (ou lead já convertido),
  retorna mensagem "já tem conta", sem duplicar.
- Conhecimento de produto: o system prompt do `LeadAgent` embute um resumo conciso de
  capacidades (de `product_faq.py`) para vender com fluência; para detalhes, expõe a tool
  `product_faq(topic)` que consulta `product_faq.lookup(topic)` — a mesma função que o help
  usa. Uma fonte, dois pontos de acesso.

Contrato de tool mantém o padrão do projeto: `{"success", "data", "message"}`, e `message`
**nunca** contém IDs, JSON ou URLs (o link de pagamento é deferido, então não há URL).

### Help para o profissional

`register_help_tools(agent)` adiciona `product_help(topic)` ao `SimplificaAgent`, retornando
orientação curada de `product_faq.py`. Sem novo agente, sem mudança de roteamento: o
profissional pergunta "como faço X?" e o agente chama a tool. Uma fonte de verdade de
"o que o produto faz" alimenta lead e help.

## Lead data flow

```
unknown number → IngestionService.handle → status="lead"
        ▼ (webhook agenda BackgroundTask)
dispatch_lead_run(inbound, record_id)
        ├─ claim atômico  UPDATE inbound_message SET agent_run_at=now()
        │                 WHERE id=record_id AND agent_run_at IS NULL   (READ COMMITTED:
        │                 exatamente um vencedor → nunca roda 2x)
        ├─ get_or_create_lead(phone)
        ├─ process_lead_message  (replay → LeadAgent.run → persist turn → fold summary)
        │     usando ChatSession com lead_id (owner = lead)
        └─ outbound.send(to=phone, text=reply)   (best-effort; falha só loga)
```

`agent_runner` é generalizado: extrai um core
`_run_with_memory(db, agent, session, deps, text) -> str` que faz replay → run → persist →
fold; `process_professional_message` e `process_lead_message` o envolvem com a sessão/deps
certas. `process_lead_message` resolve a sessão por `get_or_create_lead_session(lead_id,
phone)` e monta `LeadAgentDeps` (sem calendar/clients).

Crash-recovery de leads (orphan sweep) **não** entra neste slice — o claim atômico já
impede double-run; a varredura de leads órfãos fica como follow-up documentado (o sweep de
profissionais existente não é alterado).

## Account creation (lead → professional)

`create_professional_account`:
1. valida nome + email presentes (senão pede ao usuário via `success=False`);
2. checa idempotência: phone do lead já é `User`? lead já `converted`? → mensagem amigável,
   sem duplicar;
3. cria `User(name, email, phone=lead.phone, access_expires_at=now+trial)`;
4. `Lead.status="converted"`, `Lead.user_id=user.id`;
5. retorna `success=True` com mensagem humana (sem IDs/URL). O agente menciona que o link de
   pagamento vem depois.

Guardado pela unicidade de `users.phone_normalized` (na corrida, `IntegrityError` →
rollback → trata como "já tem conta").

## Error handling & security

- `dispatch_lead_run` e `outbound.send` são **best-effort**: logam e nunca quebram o webhook
  (sempre 200), espelhando o caminho profissional.
- Criação de conta protegida pela constraint de unicidade de phone (idempotente na corrida).
- Sem segredos hardcoded — Evolution send reusa `EVOLUTION_API_URL/KEY/INSTANCE`; novo
  `LEAD_TRIAL_DAYS`.
- Mensagens de tool sem IDs/JSON/URL (contrato existente).

## Testing strategy

**Unit**
- `Lead` model/service: `get_or_create_lead` (cria/retorna), transições de status,
  `convert_to_account` idempotente (duplicado → mesma conta, sem erro).
- `create_professional_account`: seta `access_expires_at = now + LEAD_TRIAL_DAYS`; phone
  duplicado → rejeita/idempotente; faltando email → `success=False`.
- `EvolutionOutboundAdapter.send`: monta payload certo; sem credencial → `False` sem
  levantar; erro HTTP → `False` sem levantar.
- `product_help` / `product_faq`: retorna orientação para um tópico conhecido.
- Memória de lead: `get_or_create_lead_session(lead_id, phone)` cria sessão owner=lead;
  CHECK aceita só um owner.

**Integration**
- POST Evolution de número desconhecido → `LeadAgent` roda, `leads` criado,
  turn persistido em sessão owner=lead, `outbound.send` chamado (mockado).
- Conversa de conversão → cria `User` em trial, `Lead.status=converted`, `user_id` setado.
- Inbound duplicado (mesmo `provider_message_id`) → não roda 2x.
- Profissional pergunta "como uso X?" → `SimplificaAgent` chama `product_help`.

**Live (sem Google, quando houver)**
- Conversa de lead + criação de conta usam **LLM real, sem Google** — rodável agora com
  outbound mockado. Checagem real de WhatsApp espera credenciais Evolution.

## Success criteria

- Webhook Evolution de número desconhecido dirige o `LeadAgent`, cria/atualiza o lead e
  **envia a resposta** de volta (best-effort), com o agente alheio ao provider.
- O `LeadAgent` cria a conta do profissional em trial (`access_expires_at` setado), de forma
  idempotente, e marca o lead como convertido.
- O profissional cadastrado obtém suporte via `product_help` sem novo agente nem roteamento
  por LLM.
- Redeliveries nunca rodam o lead 2x.
- Sem link de pagamento, sem outbound de profissional, sem onboarding Google neste slice.
