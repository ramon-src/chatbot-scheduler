# Agent Evals — Design (v1)

**Date:** 2026-06-23
**Status:** Approved (brainstorming)
**Branch:** `feat/agent-evals`

## Goal

Construir um harness de **avaliação dos agentes** (SimplificaAgent profissional + LeadAgent)
que sirva a dois propósitos com o mesmo eval-set:

1. **Guardrail de regressão** — travar os comportamentos bons atuais e pegar quebras
   (slot-filling, seleção de tool, recusas, formato WhatsApp) antes de irem pra produção.
2. **Seleção de modelo** — comparar candidatos **OpenAI** (`gpt-5.4-mini` atual,
   `gpt-5.4-nano`, e `gpt-5.4` full como teto de referência) por **acurácia + custo +
   latência**, pra fixar primário/fallback por evidência (princípio já no design do sistema:
   "decisões de modelo por evidência, não achismo").

O design do sistema (seção 8) já prevê isso: eval-set de ~20 conversas reais com
`pydantic-evals`. Este spec o concretiza.

## Princípios

- **LLM real** (é o ponto do eval — medir comportamento real), **opt-in** (custa tokens e
  Google), fora da suíte normal.
- **Conversas multi-turn** — cada caso é uma sequência de mensagens do usuário, não um turno
  único; é o que captura slot-filling e memória.
- **Modelo fixado por rodada** — pinar um único modelo OpenAI (não a cadeia `FallbackModel`
  inteira), pra medir aquele modelo limpo. A matriz é parametrizada (adicionar outro modelo
  = uma linha); por enquanto só OpenAI.
- **Avaliação em camadas** — determinístico onde dá (barato, estável) + LLM-juiz pro que
  asserção não alcança (qualidade conversacional/tom/formato).

## Arquitetura

```
evals/
  harness.py      # driver multi-turn contra o agente real + isolamento (user de eval, calendário persistente)
  evaluators.py   # ToolSelected, ToolArgs, DbState, NoLeakage, LLMJudge
  models.py       # catálogo de candidatos OpenAI + pin de modelo único por rodada
  datasets/       # casos por categoria (Python; pydantic_evals Case/Dataset)
  run.py          # roda dataset × matriz de modelos -> relatório
  report.py       # agrega scores por categoria/modelo + custo + latência + diff de regressão
```

Execução via `make eval [MODEL=gpt-5.4-mini] [CASE=<substring>]`, gateado por `RUN_EVAL=1`.

### Harness (driver)

`run_case(agent_factory, model_name, case) -> CaseResult`:
- monta um **usuário/lead de eval isolado** (UUID fixo de eval, distinto do dev),
- dirige a conversa turno a turno reusando o fluxo de memória de `agent_runner`
  (replay → run → persist), com o **modelo pinado** via `agent.override(model=...)`,
- coleta, ao longo de todos os turnos: as **tool calls** (nome + args + retorno, via
  `ToolReturnPart`/`ToolCallPart` do histórico), o **texto final**, e um **snapshot do estado
  do banco** relevante (cliente criado, evento, lead) — o mesmo padrão de
  `tests/live/conftest.py::_tool_returns`,
- captura **tokens/custo** (via `get_llm_run_metadata`) e **latência** por turno.

`CaseResult` (entrada dos evaluators):
```python
@dataclass
class CaseResult:
    tool_calls: list[ToolCall]      # name, args, success (todos os turnos, em ordem)
    final_output: str               # última resposta do agente
    transcript: list[Turn]          # user/assistant por turno
    db: DbSnapshot                   # cliente/evento/lead resultantes
    tokens: int
    latency_ms: int
    model: str
```

### Pin de modelo OpenAI

`models.py` expõe os candidatos e constrói um modelo **OpenAI único** (sem fallback) para o
nome dado, para `agent.override(model=...)`. Default da matriz: `["gpt-5.4-mini",
"gpt-5.4-nano"]`; `gpt-5.4` opcional via flag. Sem credencial OpenAI → o eval pula com aviso.

## Dataset (~25 casos)

Cada `Case`: `inputs` = conversa (lista de mensagens) + qual agente (lead/pro) + setup
(cliente pré-cadastrado? número conhecido?); `metadata` = expectativas; `evaluators`.

**Lead / onboarding** (LeadAgent)
- L1 dúvida de produto → responde sobre o que faz, sem inventar.
- L2 pergunta de preço → menciona teste grátis, sem URL.
- L3 criação de conta com nome+email **em mensagens separadas** → `create_professional_account`
  com os dois campos; conta em trial no banco.
- L4 já-cliente / "já tenho conta" → não duplica (idempotente).

**Cliente CRUD** (SimplificaAgent)
- C1 criar numa mensagem ("cadastra a Ana Souza, 51 98765-4321, dia 15, 220") → `create_client`
  ok; cliente no banco com os campos certos.
- C2 **slot-filling fragmentado** (telefone, depois nome, depois dia, depois preço, em msgs
  separadas) → **REGRESSÃO** do bug achado: o agente acumula e conclui sem repedir o que já
  foi dito.
- C3 buscar por nome → `find_client` retorna telefone.
- C4 mudar preço → `update_client`; preço novo no banco.
- C5 listar clientes → `list_clients` inclui o esperado.
- C6 desativar → `deactivate_client`; `is_active=False`.
- C7 **telefone duplicado** → `create_client` success=False (conflito).
- C8 **telefone inválido** → recusa/validação (success=False).
- C9 **homônimo** ("agenda a Maria" com duas Marias) → pede telefone; NÃO cria órfão.

**Agenda** (SimplificaAgent — precisa de Google real)
- A1 agendar único ("amanhã às 10h") → `create_event`; evento no horário local certo.
- A2 agendar recorrente ("toda terça às 9h") → `create_recurring_event` com RRULE semanal.
- A3 listar por período ("o que tenho amanhã?") → `list_events`; horário local correto.
- A4 cancelar → `cancel_event` success; espelho atualizado.
- A5 cancelar-com-cobrança ("cancela mas pode cobrar") → `cancel_event(charge=True)`;
  sessão fica `billable=True`.
- A6 `set_session_charge` ("não vou cobrar a sessão do dia X") → `billable=False`.
- A7 período vazio ("próxima semana") → `list_events` total 0, mensagem amigável.
- A8 cliente inexistente ("agenda o Carlos Inexistente") → recusa; nenhum evento criado.

**Formato / segurança** (transversal, aplicado a vários casos)
- F1 nenhuma resposta expõe ID/JSON/URL.
- F2 **WhatsApp-safe**: sem `**` markdown (WhatsApp usa `*` simples) — pega o nit visto no
  teste real.

Muitos casos reaproveitam as asserções já escritas em `tests/live/test_agent_live*.py`
(sementes prontas), agora estruturadas como `Case`s.

## Evaluators

- **`ToolSelected(expected_tool, success=True)`** — a tool esperada aparece nas tool_calls com
  o resultado esperado.
- **`ToolArgs(expected: dict)`** — args-chave batem (ex.: `{"consult_price": 200}`,
  `{"charge": True}`). Comparação tolerante a tipo (Decimal/str/float).
- **`DbState(check)`** — o snapshot do banco satisfaz a expectativa (cliente com os campos
  certos; evento cancelado; lead convertido). Mais forte que só a tool call.
- **`NoLeakage()`** — `final_output` (e mensagens de tool) sem IDs (UUID), JSON, URL (`http`),
  nem `**` markdown.
- **`LLMJudge(rubric)`** — juiz LLM (modelo barato e FIXO, ex.: `gpt-5.4-mini`, independente do
  modelo sob teste, pra não enviesar) dá score 0–1 + justificativa para: clareza, tom de
  assistente PT-BR, e — quando aplicável — se o slot-filling foi conduzido bem (acumulou,
  não repetiu perguntas).

Score do caso = combinação: gates determinísticos (pass/fail bloqueante) + score do juiz
(qualitativo). O relatório separa os dois.

## Mitigação da cota Google (necessária pros casos de agenda)

Hoje a fixture live **cria e deleta** um calendário secundário por execução. A cota diária de
**criação** de calendário da service account é baixa e **deleção não devolve cota** → agenda ×
N modelos × N rodadas estoura rápido.

**Mudança:** o harness reusa **um calendário fixo persistente** por usuário de eval (criado uma
vez, reaproveitado) e **limpa apenas os eventos** entre casos. Custo de criação ≈ 0 por rodada.
Esta mesma mudança conserta a fixture live atual (`tests/live/conftest.py`), que será ajustada
para o mesmo padrão (limpar eventos em vez de deletar o calendário).

## Execução & relatório

- **`make eval`** — roda o dataset completo contra a matriz (default `gpt-5.4-mini` +
  `gpt-5.4-nano`). `MODEL=` fixa um; `CASE=` filtra por substring; `RUN_EVAL=1` exigido.
- **Subconjunto sem-Google** (`make eval-fast` / tag) roda só lead+cliente+formato — barato,
  sem cota, bom pra iteração rápida e pra CI leve.
- **Relatório** (markdown + stdout): por modelo, **score por categoria**, **custo médio
  (tokens)**, **latência média**, e **diff de regressão** vs um baseline salvo
  (`evals/baselines/<model>.json`) — quais casos passaram/falharam desde a última vez.

## Plano em fases (orienta o plano de implementação)

- **Fase A (fundação):** `harness.py` + `evaluators.py` (determinístico + NoLeakage) +
  `models.py` (pin OpenAI) + casos **sem-Google** (Lead + Cliente + Formato) + `run.py`/relatório
  básico + `make eval`/`eval-fast`. Roda 1 modelo. Inclui o caso de regressão de slot-filling.
- **Fase B (agenda):** calendário persistente no harness (+ conserto da fixture live) + casos
  de agenda (A1–A8) + `DbState` para eventos.
- **Fase C (matriz + juiz):** `LLMJudge` + execução multi-modelo (mini/nano) + relatório
  comparativo + baselines/diff de regressão.

## Testing strategy

- O **harness e os evaluators** têm testes unitários **sem LLM** (com `FunctionModel` e
  `CaseResult` sintéticos): provam que `ToolSelected`/`ToolArgs`/`NoLeakage`/`DbState`
  pontuam certo, e que o driver coleta tool_calls/transcript corretamente.
- O **eval-set real** (LLM) não roda na suíte normal — é o produto do harness, rodado via
  `make eval`.

## Out of scope (v1)

- Modelos não-OpenAI (claude-haiku etc.) — a matriz fica parametrizada, mas sem candidatos
  não-OpenAI agora.
- Evals **end-to-end de roteamento/memória** (ingestão→dispatch, ex.: split lead→pro) — os
  testes de integração já cobrem; fica pra depois.
- Dashboard/UI — relatório em texto/markdown.
- Fiscal (fase futura do produto).

## Success criteria

- `make eval-fast` roda os casos sem-Google contra `gpt-5.4-mini` com LLM real e produz um
  relatório com score por categoria, custo e latência.
- O caso de slot-filling fragmentado (C2) é um gate determinístico que **falharia** no
  comportamento antigo e **passa** no atual — provando o valor de regressão.
- Os casos de agenda rodam reaproveitando **um calendário persistente** (zero criação de
  calendário por rodada).
- Adicionar um modelo OpenAI candidato à matriz é uma mudança de uma linha.
