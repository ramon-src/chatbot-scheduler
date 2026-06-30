# Summary Cleaning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the conversation summarizer correct and prune junk (off-domain, superseded data, dead threads, technical leakage) while it folds, keeping the running summary a clean, lean record.

**Architecture:** One behavior change in `app/agents/summarizer.py` (rewrite of `SUMMARY_SYSTEM_PROMPT`); the call site, models, and memory flow are untouched. A deterministic eval suite in `evals/` (gated by `RUN_EVAL=1`) verifies both that junk is removed and that core facts survive.

**Tech Stack:** Python 3.11+, Pydantic AI (`Agent`, `Model`), pydantic_evals (`Case`, `Dataset`, custom `Evaluator`), pytest, uv.

## Global Constraints

- Código/identificadores/enums em inglês; mensagens ao usuário final e prompts em PT-BR.
- Summarizer output contract (unchanged): PT-BR, poucas frases, texto simples, sem IDs, JSON, URLs ou markdown.
- No change to the memory flow, call sites, thresholds, models, or storage. `summarize_conversation` keeps its exact signature `(existing_summary, messages, model=None) -> str`.
- Summary-only scope: do NOT touch the raw-history replay path (`RAW_HISTORY_LIMIT`, `_run_with_memory`).
- Evals run real LLM, gated by `RUN_EVAL=1` + `OPENAI_API_KEY`; default model `gpt-5.4-mini`; `evaluate_sync(task, max_concurrency=1)`.
- No secrets in code. Commits never attribute to AI.
- Core-preservation latch: active clients + final data, valid appointments, and open actionable pendencies are ALWAYS kept, even under the aggressive trim bias.

---

### Task 1: Rewrite the summarizer prompt

**Files:**
- Modify: `app/agents/summarizer.py` (the `SUMMARY_SYSTEM_PROMPT` constant only)
- Test: `tests/unit/test_summarizer.py` (create)

**Interfaces:**
- Consumes: `build_summary_input(existing_summary: str | None, messages: list[ChatMessage]) -> str` (unchanged), `ChatMessage` (reads `.message_type`, `.content`).
- Produces: nothing new; `summarize_conversation` keeps signature `(existing_summary, messages, model=None) -> str`.

The prompt is content verified behaviorally by the Task 3 eval. The unit test here locks the deterministic transcript contract the prompt depends on (currently untested code).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_summarizer.py`:

```python
"""Unit tests for the summarizer transcript builder (LLM-free)."""

from app.agents.summarizer import build_summary_input
from app.models.chat_session import ChatMessage


def _msg(role: str, content: str) -> ChatMessage:
    return ChatMessage(message_type=role, content=content)


def test_build_summary_input_maps_roles_and_header():
    text = build_summary_input(
        existing_summary="Resumo anterior aqui.",
        messages=[_msg("user", "ola"), _msg("assistant", "oi, tudo bem?")],
    )
    assert "Resumo anterior: Resumo anterior aqui." in text
    assert "Novas mensagens:" in text
    assert "Profissional: ola" in text
    assert "Assistente: oi, tudo bem?" in text


def test_build_summary_input_without_existing_summary_omits_prefix():
    text = build_summary_input(existing_summary=None, messages=[_msg("user", "ola")])
    assert "Resumo anterior:" not in text
    assert text.startswith("Novas mensagens:")
```

- [ ] **Step 2: Run test to verify it passes (characterization)**

Run: `uv run pytest tests/unit/test_summarizer.py -v`
Expected: PASS (it characterizes the existing, unchanged `build_summary_input`). If it fails, the transcript contract differs from the spec — stop and reconcile before editing the prompt.

- [ ] **Step 3: Rewrite the prompt**

In `app/agents/summarizer.py`, replace the `SUMMARY_SYSTEM_PROMPT` constant (lines 16–19) with:

```python
SUMMARY_SYSTEM_PROMPT = """Você mantém um resumo vivo da conversa entre um psicólogo e seu assistente de consultório.
A cada rodada você recebe o resumo anterior e as novas mensagens e devolve o resumo ATUALIZADO.

PRESERVE (núcleo — mantenha SEMPRE, mesmo enxugando):
- Clientes ativos e seus dados finais: nome, telefone, dia de cobrança, preço da consulta.
- Agendamentos válidos: cliente, data e hora.
- Pendências em aberto e acionáveis (ex.: "cadastro da Ana aguardando o telefone").

FAÇA FAXINA (corrija e descarte ao dobrar):
- Fora de domínio: descarte qualquer trecho que não seja sobre clientes, agenda ou cobrança
  (programação, SQL, banco de dados, devops, assuntos gerais), inclusive a recusa do assistente. Não vira memória.
- Dado substituído: se um valor foi corrigido (ex.: preço 200 e depois 250, telefone trocado),
  mantenha SÓ o valor final; o antigo some.
- Fio morto: tentativas superadas ou que não levaram a nada saem.
- Vazamento técnico: nunca inclua IDs, códigos, JSON, URLs ou markdown.

VIÉS: na dúvida entre manter um detalhe de borda ou enxugar, enxugue. Mas pendência acionável
NÃO é fio morto — preserve.

FORMATO: Português do Brasil, poucas frases, texto simples, sem IDs, JSON, URLs ou markdown."""
```

- [ ] **Step 4: Run the unit test and the full unit suite**

Run: `uv run pytest tests/unit/test_summarizer.py -v`
Expected: PASS (prompt change does not affect the deterministic builder).

Run: `uv run pytest -p no:warnings -q`
Expected: PASS (no regressions; same counts as before plus the 2 new tests).

- [ ] **Step 5: Commit**

```bash
git add app/agents/summarizer.py tests/unit/test_summarizer.py
git commit -m "feat: summarizer cleans junk while folding the summary"
```

---

### Task 2: Add string evaluators for summary output

**Files:**
- Modify: `evals/evaluators.py` (append two evaluators)
- Test: `tests/unit/test_summary_evaluators.py` (create)

**Interfaces:**
- Consumes: `pydantic_evals.evaluators.Evaluator`, `EvaluatorContext` (reads `ctx.output` as a `str`).
- Produces: `ExcludesAll(tokens: list[str])`, `IncludesAll(tokens: list[str])` — both case-insensitive substring checks over the string output, used by the summary suite (Task 3).

These differ from the existing evaluators (which read `ctx.output.final_output`/`.tool_calls`/`.db` on a `CaseResult`); the summary suite's output is a plain `str`, so these read `ctx.output` directly.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_summary_evaluators.py`:

```python
"""Unit tests for the string-membership summary evaluators."""

from types import SimpleNamespace

from evals.evaluators import ExcludesAll, IncludesAll


def _ctx(output: str):
    return SimpleNamespace(output=output)


def test_excludes_all_true_when_no_token_present():
    assert ExcludesAll(tokens=["SQL", "select"]).evaluate(_ctx("Cliente Ana, 220 reais.")) is True


def test_excludes_all_false_when_any_token_present_case_insensitive():
    assert ExcludesAll(tokens=["SQL"]).evaluate(_ctx("ajuda com sql aqui")) is False


def test_includes_all_true_when_every_token_present():
    assert IncludesAll(tokens=["Ana", "250"]).evaluate(_ctx("Ana agora paga 250")) is True


def test_includes_all_false_when_a_token_missing():
    assert IncludesAll(tokens=["Ana", "250"]).evaluate(_ctx("Ana agora paga 200")) is False


def test_evaluators_tolerate_empty_output():
    assert ExcludesAll(tokens=["x"]).evaluate(_ctx("")) is True
    assert IncludesAll(tokens=["x"]).evaluate(_ctx("")) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_summary_evaluators.py -v`
Expected: FAIL with `ImportError: cannot import name 'ExcludesAll'`.

- [ ] **Step 3: Implement the evaluators**

Append to `evals/evaluators.py`:

```python
@dataclass
class ExcludesAll(Evaluator):
    """Pass when NONE of the tokens appear in the string output (case-insensitive)."""

    tokens: list[str]

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        text = (ctx.output or "").lower()
        return all(t.lower() not in text for t in self.tokens)


@dataclass
class IncludesAll(Evaluator):
    """Pass when EVERY token appears in the string output (case-insensitive)."""

    tokens: list[str]

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        text = (ctx.output or "").lower()
        return all(t.lower() in text for t in self.tokens)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_summary_evaluators.py -v`
Expected: PASS (all 5).

- [ ] **Step 5: Commit**

```bash
git add evals/evaluators.py tests/unit/test_summary_evaluators.py
git commit -m "feat: add ExcludesAll/IncludesAll evaluators for summary output"
```

---

### Task 3: Summary-cleaning eval suite and runner wiring

**Files:**
- Modify: `evals/harness.py` (append `SummaryInputs` dataclass + `run_summary_case`)
- Create: `evals/datasets/summary_cleaning.py`
- Modify: `evals/run.py` (add `--suite` selection)
- Modify: `Makefile` (add `eval-summary` target)
- Test: `tests/unit/test_run_summary_case.py` (create)

**Interfaces:**
- Consumes: `summarize_conversation` (Task 1), `ExcludesAll`/`IncludesAll` (Task 2), `build_eval_model(alias)` (existing, returns `OpenAIChatModel`), `ChatMessage`.
- Produces: `SummaryInputs(messages: list[tuple[str, str]], existing_summary: str | None = None)`, `async run_summary_case(inputs: SummaryInputs, model) -> str`, `build_summary_cleaning_dataset() -> Dataset`.

- [ ] **Step 1: Write the failing test (deterministic, no real LLM)**

Create `tests/unit/test_run_summary_case.py`. It drives `run_summary_case` against a `FunctionModel` so it stays LLM-free and deterministic:

```python
"""run_summary_case wires SummaryInputs -> summarize_conversation (LLM-free via FunctionModel)."""

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from evals.harness import SummaryInputs, run_summary_case


def _echo_first_user(messages, info):
    # The transcript is the single user prompt build_summary_input produced.
    prompt = messages[-1].parts[-1].content
    return ModelResponse(parts=[TextPart(content=f"RESUMO::{prompt}")])


@pytest.mark.asyncio
async def test_run_summary_case_feeds_transcript_to_model():
    model = FunctionModel(_echo_first_user)
    out = await run_summary_case(
        SummaryInputs(
            existing_summary="Cliente Bruno, 200 reais.",
            messages=[("user", "passou pra 250"), ("assistant", "feito")],
        ),
        model,
    )
    assert out.startswith("RESUMO::")
    assert "Resumo anterior: Cliente Bruno, 200 reais." in out
    assert "Profissional: passou pra 250" in out
    assert "Assistente: feito" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_run_summary_case.py -v`
Expected: FAIL with `ImportError: cannot import name 'SummaryInputs'`.

- [ ] **Step 3: Implement `SummaryInputs` + `run_summary_case`**

Append to `evals/harness.py` (mirror the existing `CaseInputs` dataclass style; add imports if missing):

```python
@dataclass
class SummaryInputs:
    """Inputs for a summarizer-cleaning eval case."""

    messages: list[tuple[str, str]]  # (role, content); role in {"user", "assistant"}
    existing_summary: str | None = None


async def run_summary_case(inputs: SummaryInputs, model) -> str:
    """Fold a dirty transcript through the real summarizer and return the summary string."""
    from app.agents.summarizer import summarize_conversation
    from app.models.chat_session import ChatMessage

    msgs = [ChatMessage(message_type=role, content=content) for role, content in inputs.messages]
    return await summarize_conversation(inputs.existing_summary, msgs, model=model)
```

(`from dataclasses import dataclass` is already imported in `evals/harness.py`; reuse it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_run_summary_case.py -v`
Expected: PASS.

- [ ] **Step 5: Create the dataset**

Create `evals/datasets/summary_cleaning.py`:

```python
"""Summary-cleaning eval cases: junk removed, core facts kept."""

from __future__ import annotations

from pydantic_evals import Case, Dataset

from evals.evaluators import ExcludesAll, IncludesAll
from evals.harness import SummaryInputs


def build_summary_cleaning_dataset() -> Dataset:
    cases = [
        Case(
            name="limpa_fora_dominio",
            inputs=SummaryInputs(messages=[
                ("user", "cadastrei a Ana Souza, telefone 51 98765-4321, dia 15, 220 reais"),
                ("user", "me ajuda a escrever uma query SQL SELECT * FROM usuarios no postgres?"),
                ("assistant", "Desculpa, eu cuido só do seu consultório — clientes, agenda e cobrança."),
            ]),
            evaluators=[ExcludesAll(tokens=["SELECT", "SQL", "postgres"]),
                        IncludesAll(tokens=["Ana"])],
        ),
        Case(
            name="limpa_dado_substituido",
            inputs=SummaryInputs(
                existing_summary="Cliente Bruno Lima, consulta 200 reais, dia 10.",
                messages=[("user", "na verdade a consulta do Bruno passou pra 250")],
            ),
            evaluators=[ExcludesAll(tokens=["200"]), IncludesAll(tokens=["250", "Bruno"])],
        ),
        Case(
            name="limpa_fio_morto",
            inputs=SummaryInputs(messages=[
                ("user", "quero agendar um horario"),
                ("assistant", "Claro, para qual cliente e quando?"),
                ("user", "deixa pra la, esquece isso"),
                ("user", "muda o preço da Carla Dias para 300"),
            ]),
            evaluators=[ExcludesAll(tokens=["esquece", "deixa pra la"]),
                        IncludesAll(tokens=["Carla", "300"])],
        ),
        Case(
            name="limpa_vazamento_tecnico",
            inputs=SummaryInputs(messages=[
                ("user", "confirma o cadastro da Diana Reis"),
                ("assistant", "Cadastrei a Diana Reis (id 4f8c2a1e-9b7d-4c3a-8e21-aa1122334455) com sucesso"),
            ]),
            evaluators=[ExcludesAll(tokens=["4f8c2a1e"]), IncludesAll(tokens=["Diana"])],
        ),
        Case(
            name="preserva_pendencia_aberta",  # aggressive bias must NOT drop an open pendency
            inputs=SummaryInputs(messages=[
                ("user", "quero cadastrar a Ana Beatriz"),
                ("assistant", "Perfeito. Qual o telefone, o dia de cobrança e o valor da consulta da Ana Beatriz?"),
            ]),
            evaluators=[IncludesAll(tokens=["Ana Beatriz"])],
        ),
    ]
    return Dataset(name="summary_cleaning", cases=cases)
```

- [ ] **Step 6: Wire the `--suite` flag into the runner**

In `evals/run.py`, change the signature and the dataset/task selection. Replace the body of `main` from the `from evals.harness import run_case` line through the `report = ...` line with:

```python
    model = build_eval_model(model_alias)

    if suite == "summary":
        from evals.datasets.summary_cleaning import build_summary_cleaning_dataset
        from evals.harness import run_summary_case

        dataset = build_summary_cleaning_dataset()

        async def task(inputs):
            return await run_summary_case(inputs, model)
    else:
        from evals.harness import run_case

        dataset = build_google_free_dataset()

        async def task(inputs):
            return await run_case(inputs, model)

    if case_filter:
        dataset.cases = [c for c in dataset.cases if case_filter in c.name]

    report = dataset.evaluate_sync(task, max_concurrency=1)
```

Update the `main` signature to:

```python
def main(model_alias: str = "gpt-5.4-mini", case_filter: str | None = None, suite: str = "agent") -> int:
```

And the argparse block at the bottom:

```python
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="gpt-5.4-mini")
    p.add_argument("--case", default=None)
    p.add_argument("--suite", default="agent", choices=["agent", "summary"])
    args = p.parse_args()
    sys.exit(main(args.model, args.case, args.suite))
```

- [ ] **Step 7: Add the Makefile target**

In `Makefile`, after the `eval` target (line ~116), add:

```makefile
eval-summary: ## Rodar o eval de faxina do resumo (LLM real; usage: make eval-summary [MODEL=gpt-5.4-mini] [CASE=<substr>])
	@RUN_EVAL=1 $(UV) run python -m evals.run --suite summary --model $(or $(MODEL),gpt-5.4-mini) $(if $(CASE),--case $(CASE),)
```

- [ ] **Step 8: Run the unit suite (deterministic gate)**

Run: `uv run pytest -p no:warnings -q`
Expected: PASS (all prior tests plus the new unit tests; no regressions).

- [ ] **Step 9: Run the real eval (behavioral gate)**

Run: `make eval-summary`
Expected: the summary suite runs against `gpt-5.4-mini`; the printed summary reports the per-case PASS/FAIL. Record the result honestly in the ledger — a model that ignores a cleaning rule is a real finding, not a reason to weaken an assertion. (Requires `RUN_EVAL=1`, which the target sets, and `OPENAI_API_KEY` in `.env`.)

- [ ] **Step 10: Commit**

```bash
git add evals/harness.py evals/datasets/summary_cleaning.py evals/run.py Makefile tests/unit/test_run_summary_case.py
git commit -m "feat: add summary-cleaning eval suite and runner"
```

---

## Self-Review

**Spec coverage:**
- Prompt rewrite with 4 cleaning rules + aggressive bias + core-preservation latch → Task 1.
- Deterministic unit over `build_summary_input` → Task 1.
- Deterministic eval (dirty transcripts; negative + positive asserts) → Tasks 2 (evaluators) + 3 (dataset, runner, Makefile).
- Output contract unchanged (PT-BR, no leakage) → preserved in prompt FORMATO line; `NoLeakage`-style negative asserts via `ExcludesAll`.
- Out-of-scope (raw history, call sites, models) → Global Constraints forbid touching them; no task does.

**Placeholder scan:** none — every code step shows full content.

**Type consistency:** `summarize_conversation(existing_summary, messages, model=None) -> str` consistent across tasks; `SummaryInputs(messages, existing_summary=None)` and `run_summary_case(inputs, model) -> str` match between harness, dataset, runner, and tests; `ExcludesAll(tokens=...)`/`IncludesAll(tokens=...)` consistent between Task 2 definition and Task 3 dataset use.
