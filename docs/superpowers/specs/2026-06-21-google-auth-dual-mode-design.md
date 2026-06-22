# Google Auth — Dual Mode (Service Account default + OAuth opt-in)

**Status:** approved (Ramon, 2026-06-21)
**Extends:** `2026-06-21-simplifica-agent-system-design.md` §5.2 / §11; builds on the agenda slice (`feat/agenda-google-calendar`).

## 1. Objetivo

Permitir que cada profissional comece a usar a agenda **sem nenhuma fricção** (sem login/consentimento), e ainda assim possa, opcionalmente, conectar a própria conta Google depois. Dois modos de autenticação coexistem; o **service account é o padrão**.

## 2. Decisão

Resolução de acesso ao calendário **por usuário, a cada mensagem**:

```
resolve_calendar_access(user):
  1. usuário tem credencial OAuth própria (linha em google_credentials)?
        → usa a agenda PRINCIPAL dele (calendarId="primary")        [upgrade opcional]
  2. senão, service account configurada no ambiente?
        → usa/cria um calendário dele SOB a nossa service account    [PADRÃO — fricção zero]
  3. senão
        → não conectado (as tools degradam graciosamente)
```

- Com a SA configurada **uma vez por nós** (`GOOGLE_CLIENT_EMAIL` + `GOOGLE_PRIVATE_KEY` no `.env`), todo profissional já começa funcionando.
- O OAuth do usuário, **quando existir, tem prioridade** sobre a SA.

## 3. Modelo de calendário

- **SA mode:** na primeira vez, criamos um calendário dedicado ao profissional sob a service account (`calendars.insert`, summary `"SimplificaPsi — {nome}"`) e gravamos o **`google_calendar_id` real** (ex.: `...@group.calendar.google.com`) na tabela `calendars` (`is_primary=True`). Reusa nas próximas.
  - **Compartilhamento best-effort:** logo após criar, compartilhamos o calendário com o e-mail do profissional (`acl.insert`, role `writer`) **se** `User.email` existir. Falha de compartilhamento (e-mail não-Google, etc.) é ignorada — não bloqueia. Assim o profissional vê os eventos no app nativo do Google quando possível.
- **OAuth mode:** `google_calendar_id="primary"` (a agenda principal da conta dele).

## 4. Arquitetura (strategy)

```
GoogleAuthStrategy (porta conceitual)
├── service account credentials  → app/services/google_auth.py: build_service_account_credentials(), service_account_available()
└── user OAuth credentials       → app/services/google_auth.py: load_credentials(), has_credentials()   [já existe]

calendar_provider.build_calendar_access(db, user, settings) -> CalendarAccess | None
   - escolhe o modo conforme a regra §2
   - SA: garante o calendário do profissional (find-or-create + share best-effort)
   - retorna (GoogleCalendarService já vinculado ao calendarId certo, Calendar row local)

GoogleCalendarService (+ create_calendar, + share_calendar)   [estende o da fatia de agenda]
EventService (+ ensure_calendar para upsert do google_calendar_id real)   [estende]
agent_routes  → usa build_calendar_access em vez do bloco OAuth inline
```

- **Tudo testável sem rede:** credenciais e o recurso da API do Google são injetados/mockados; nenhum teste acessa o Google.
- `EventService.record_event` continua usando a `Calendar` row local para o FK `Event.calendar_id`; o provider garante que essa row tenha o `google_calendar_id` correto **antes** de qualquer operação, então as duas pontas (Google + Postgres) ficam consistentes.

## 5. Credenciais service account

- Origem: `GOOGLE_CLIENT_EMAIL` + `GOOGLE_PRIVATE_KEY` no `.env` (mesmo formato do legado TS). `GOOGLE_PRIVATE_KEY` com `\n` escapado → `.replace("\\n", "\n")`.
- Construção: `google.oauth2.service_account.Credentials.from_service_account_info({...}, scopes=["https://www.googleapis.com/auth/calendar"])`.
- Escopo `calendar` (preciso criar calendários + acl), não só `calendar.events`.

## 6. Guard-rails e contrato (inalterados)

- Tools continuam retornando `{success,data,message}`; `message` nunca vaza IDs/URLs (o `google_calendar_id` real **nunca** vai para `message`).
- Evento exige cliente cadastrado; degradação graciosa quando não conectado; dual-write com compensação (já implementado na fatia de agenda).

## 7. Limitações conscientes do v1

- **Troca de modo não migra eventos:** se um profissional usar SA e depois conectar OAuth, eventos antigos ficam no calendário da SA e novos vão para a agenda pessoal. Migração/reconciliação fica fora de escopo (futura fatia).
- **SA não-Workspace:** criamos calendários secundários sob a SA (como o legado). *Domain-wide delegation* (impersonar a conta do profissional) não é usado — não se aplica a Gmail pessoal.
- Leitura (`list_events`/`cancel_event`) continua pelo espelho Postgres (decisão da fatia de agenda).

## 8. Fora de escopo

- Fluxo de "upgrade" guiado (mandar link de OAuth no WhatsApp) — a infra (`scripts/google_auth.py`) já existe; o gatilho conversacional fica para a fatia de WhatsApp/onboarding.
- Revogação/limpeza de calendários órfãos da SA.
