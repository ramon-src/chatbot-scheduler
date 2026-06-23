---
name: task-tracking
description: Use when implementing a plan from docs/superpowers/plans/ task-by-task — enforces the loop develop → write test → green → mark the task done in the plan's tasks.md, keeping it the live source of truth for progress.
---

# Task Tracking

> Adapted from the Rooster `task-tracking` skill. This repo keeps plans/specs in
> `docs/superpowers/{plans,specs}/` (per `CLAUDE.md`), **not** in an `openspec/`
> tree. The loop and Definition of Done are the same; only the file location differs.

## Where progress lives

Each plan in `docs/superpowers/plans/<date>-<slug>.md` is the **macro** view
(phases + goal). For an in-flight plan, keep a sibling **granular tracker**:

```
docs/superpowers/plans/<date>-<slug>.md          ← macro phases (already exists)
docs/superpowers/plans/<date>-<slug>.tasks.md    ← granular checkboxes (add this)
```

`*.tasks.md` is the live source of truth for progress; the plan's phase checkboxes
are the rolled-up macro view. Keep both honest. (If a plan already embeds its task
checkboxes inline, that file IS the tracker — no separate `.tasks.md` needed.)

## The loop (per task)

Do this for each task, in order:

1. **Develop** the task — implementation code only.
2. **Write the test** (invoke `test-as-spec`) that proves the task's behavior.
   For a bugfix, follow the repo's Bug-Fix TDD protocol: failing test first (red).
3. **Run the test** (`make test` / `make test-unit`) and confirm it is **green**.
4. **Only now** mark that task `- [x]` in the tracker. A task whose test is not
   green is NOT done — do not check it.
5. Commit (the work + the updated tracker), one commit per task (per `CLAUDE.md` §5).

**Definition of Done = implementation + test written + test green.** Nothing gets
a `- [x]` without a passing test behind it.

## The rollup (at commit / push)

Before a `git commit` / `git push` lands:

1. Ensure every finished task is `- [x]` in the tracker.
2. Update the plan's macro phase checkboxes to mirror it — tick a phase `- [x]`
   once all its tasks are done.

Tasks change task-by-task; macro phases change phase-by-phase at commit/push.

## Tracker format

```markdown
# <Human Title> — Tasks

> Definition of Done per task: implementation → test written (test-as-spec) → green.
> Only then mark `- [x]`. Roll up into the plan's phases at commit/push.

## Phase 1 — <macro phase name, mirrors the plan>

- [ ] <task — what ships + the behavior its test proves>
- [ ] <task>

## Phase 2 — <macro phase name>

- [ ] <task>
```

## Branch ↔ plan convention

Name feature branches `<type>/<slug>` so the slug matches the plan file
(`feat/lead-help-outbound` → `docs/superpowers/plans/2026-06-22-lead-help-outbound.md`).
This keeps "which plan am I working on" derivable from the branch.
