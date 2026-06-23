---
name: devils-advocate
description: Use at the end of development work, before declaring anything done, fixed, or working — code written/edited, bug fixed, feature implemented. Self-interrogates the just-completed work as a hostile reviewer across business goal, contracts, infra, architecture, edge cases, and tests to surface what would break it.
---

# Devil's Advocate

> Adapted from the Rooster `devils-advocate` for this single-repo Python/agent
> project. The six lenses are the same; the cross-references point at this repo's
> reality (Google Calendar source-of-truth, dual-write, tools contract, Alembic)
> instead of the Rooster multi-repo `_meta/` indexes.

## Overview

Before declaring dev work done, become the hostile reviewer of your *own*
just-completed work. The goal: find what you are NOT seeing — what could make all
of it break — while existing flows must stay 100%.

**Core principle: evidence, not optimism.** Every claim is backed by something you
actually ran, read, or traced — or it becomes an open risk. "Should work" /
"probably fine" / "I assume" are forbidden answers.

## When to Use

- After writing/editing code, fixing a bug, or implementing a feature — before
  saying "pronto", "done", "fixed", "working", or committing.
- NOT for non-dev conversations (questions, exploration, planning).

## The Six Lenses

Ask each hostile question out loud, then answer it with concrete evidence.

### 🎯 1. Business goal
- Does this solve what was *actually* asked — or what was convenient to build?
- Did I drift from the objective mid-implementation?
- Did I fix the root cause or just silence the symptom?
- User-facing messages in PT-BR, no IDs/JSON/URLs leaked (per the tool contract)?

### 📜 2. Contracts
- Did I change a **tool's** return shape? Every tool must return
  `{"success": bool, "data": Any, "message": str}` and `message` must not contain
  IDs/JSON/HTML/markdown/URLs (`CLAUDE.md` §5).
- Did I change the agent's system prompt or a tool signature the LLM relies on?
- Inbound/outbound message ports stay provider-agnostic (no Evolution/Meta
  specifics leaking into the agent)?

### 🔧 3. Infra
- New env var, Alembic migration, DB index, secret, ordering dependency?
- Migration: is it reversible (`downgrade` correct)? Did I edit `init-db.sql`
  instead of a migration? (Schema = Alembic, single source — `CLAUDE.md` §7.)
- **Observability:** if this breaks in prod, is there a log to diagnose it — or
  does it fail silently?
- **Google dual-write:** does the compensation/rollback path still hold (Google
  writes first; Postgres failure removes the orphan event best-effort)?

### 🏛️ 4. Architecture
- Did I reintroduce a legacy layer (intent-parser / manager / formatter)? Forbidden.
- Single-agent-with-tools preserved — no second reasoning hop added?
- Guard-rails kept in code (tools/services/schemas), not delegated to the LLM
  (phone validation, "event requires existing client", soft-delete with reason)?
- Did I invent an LLM model id instead of using the catalog in
  `app/agents/foundation/llm.py`?

### 💥 5. Edge cases & flows
- **What could make all of this break?** Name the failure honestly.
- Existing flows kept 100%? Trace the ones this touches (create/cancel event,
  client CRUD, conversation memory replay/fold).
- Nulls, concurrency, partial failure, retries, idempotency, timezone
  (`America/Sao_Paulo`), week-starts-Sunday?

### 🧪 6. Tests & observable behavior
- Is there a test that *proves* this? (Bug fix → the test must have failed RED
  before the fix.)
- Is the test a real spec — `given/when/then`, `feature`/`module` markers
  (`test-as-spec`) — or does it just pass?
- Did I run the **whole suite** (`make test`), not only the new test? Where is the
  output?
- Did any **existing** test break? Did I mock/loosen anything just to get green?
- Sad path covered (error, null, timeout, calendar failure degrading gracefully)?
- Silent regression for current users?

## Output

After the six lenses:

1. **Clear fixes → apply now.** A bug follows the TDD protocol: failing test (RED)
   → fix → confirm green.
2. **Everything ambiguous → list under `⚠️ Riscos que precisam da sua decisão`**
   with the specific question for the user.
3. **All clean → declare done WITH the evidence attached** (tests run + output,
   files traced).

## Red Flags — you are rationalizing

| Thought | Reality |
|---|---|
| "Should work" / "probably fine" | Not evidence. Run it or trace it, or it's an open risk. |
| "I already tested it" | Which test? Did it fail before the fix? Did the full suite pass? |
| "It's a small change" | Small changes break contracts and flows too. Run the lenses. |
| "Not worth interrogating" | The cheap bugs are the ones you didn't look for. |
| "I'll skip lenses that don't apply" | State *why* each lens doesn't apply — that IS the check. |

Skipping a lens silently = skipping the review. Name every lens, even if the answer
is "not affected, because X".
