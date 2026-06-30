# Summary Cleaning — Design

**Date:** 2026-06-23
**Status:** Approved (design); pending implementation plan
**Owner component:** `app/agents/summarizer.py`

## Problem

The conversation summarizer (`summarize_conversation`) folds overflow turns
into a running PT-BR summary that is injected into the agent's system prompt as
"Resumo da conversa até aqui". Today it only **preserves** what matters; it has
no mandate to **clean**. As a result, junk accumulates in long-lived memory:

- Off-domain exchanges (devops, SQL, general chit-chat) — the same class of
  content that previously contaminated in-context history and taught the model
  to answer off-domain.
- Superseded data — a value the professional gave and later corrected (price
  200 → 250, a changed phone), with the stale value lingering.
- Dead threads — collections that were abandoned or superseded, questions that
  led nowhere.
- Technical leakage — IDs, JSON, URLs, markdown that slipped into the summary.

## Goal

Make the summarizer **correct and prune** while it folds, so the running summary
stays a clean, faithful, lean record of the professional's practice state.

## Scope

**In scope:** behavior change to the summarizer prompt (`SUMMARY_SYSTEM_PROMPT`)
plus tests/evals. One component.

**Out of scope (explicitly deferred):**
- Cleaning the recent **raw** messages replayed verbatim (the ~10 within
  `RAW_HISTORY_LIMIT`). Decision: summary-only. Consequence: recent raw turns
  still reach the model dirty until they overflow into the summary. Accepted.
- Any change to the memory flow, thresholds, models, or storage. The trigger
  (`agent_runner._maybe_update_summary` on overflow) is unchanged.
- A second LLM pass or per-message filtering. No added per-message cost.

## Architecture

The change is contained in `app/agents/summarizer.py`:

- `build_summary_input(existing_summary, messages)` — unchanged. Deterministic
  transcript builder, LLM-free, testable.
- `summarize_conversation(...)` — unchanged signature and call site. Only the
  system prompt it runs under changes.
- `SUMMARY_SYSTEM_PROMPT` — rewritten to add the four cleaning rules, the
  aggressive bias, and the core-preservation safety latch.

No change to `agent_runner.py`, `chat_history_service.py`, or any model/schema.

## Cleaning behavior (new prompt mandate)

The summarizer, while folding, applies four cleaning rules:

1. **Off-domain** → drop any stretch that is not about clients, agenda, or
   billing (devops, SQL, env vars, general advice, chit-chat), **including the
   agent's refusal of it**. It must not become memory.
2. **Superseded data** → when a value was corrected (price 200 → 250, a changed
   phone or invoice day), keep **only the final value**; the old one disappears.
3. **Dead thread / noise** → attempts that were superseded or led nowhere are
   removed.
4. **Technical leakage** → IDs, JSON, URLs, markdown never enter the summary
   (existing rule, reinforced).

**Aggressive bias:** when in doubt between keeping an edge detail and trimming,
trim. Keep the summary lean.

**Core-preservation safety latch (always kept, even under the aggressive bias):**
- active clients and their final data (name, phone, invoice day, consult price);
- valid scheduled appointments;
- **open, actionable pendencies** (e.g. "cadastro da Ana aguardando telefone").

An open actionable pendency is **not** a dead thread. This latch is what keeps
the aggressive bias from breaking incremental slot-filling: a half-collected
registration that is still waiting on a field is core information, not noise.

## Output contract (unchanged)

PT-BR, few sentences, no IDs/JSON/URLs/markdown. The summary remains a plain
string returned by `summarize_conversation`.

## Testing

The summarizer splits into a deterministic part and one LLM call; both sides are
testable.

1. **Deterministic unit** over `build_summary_input` (no LLM): asserts the
   transcript format — existing-summary line, "Novas mensagens:" header,
   Profissional/Assistente role mapping. (Guards the input contract the prompt
   relies on.)
2. **Deterministic eval** in the existing harness (`evals/`, gated by
   `RUN_EVAL=1` + `OPENAI_API_KEY`, run via `make eval-fast`): dirty transcripts
   →
   - **negative asserts**: the produced summary does **not** contain the junk of
     each of the four categories (off-domain token, the stale value, the dead
     thread, technical leakage);
   - **positive asserts**: the summary **still** contains the core facts (client
     name, final value, the open pendency).

   The positive asserts are the safety net for the aggressive bias: they fail
   loudly if cleaning starts eating real information.

The eval cases are deterministic (string-membership checks on the summary), not
LLM-judge, matching the Phase A harness style.

## Risks

- **Over-deletion** (aggressive bias eats real info) → mitigated by the
  core-preservation latch in the prompt and the positive eval asserts.
- **Model ignores a rule** (as gpt-5.4-mini did with the no-markdown rule) →
  the eval surfaces it honestly rather than hiding it; deterministic
  sanitization of leakage remains a possible follow-up, out of scope here.

## Success criteria

- Off-domain, superseded, dead-thread, and leakage content is absent from the
  folded summary on the eval transcripts.
- Client final data, valid appointments, and open pendencies survive folding.
- No change to the memory flow, call sites, or per-message cost.
