---
name: test-as-spec
description: Use when writing or refactoring pytest tests (test_*.py / *_test.py) so they double as executable specification. Enforces BDD-lite naming (given/when/then), feature/module tags via pytest markers, inline setup, and explicit asserts — optimized for fast navigation of behavior across the codebase.
---

# Test as Spec (pytest)

Make tests readable as a **specification of behavior**. Goal: fast navigation by
tags + top-down readability per file, so an agent (or human) can answer "what does
this module do?" by reading the tests — without extra documentation.

> Adapted from the Rooster `test-as-spec` (Vitest/Jest) for this repo's stack:
> **Python 3.11+ / pytest / pytest-asyncio**. The BDD-lite structure is identical;
> only the mechanics (classes instead of `describe`, markers instead of tag-strings)
> are pythonic.

All test artifacts (class names, test names, fixtures, comments, tags) are written
in **English**, regardless of the product's PT-BR UI (per `CLAUDE.md` §5).

## When to apply

- Any new `test_*.py` / `*_test.py` you write.
- Any test file you're already modifying (boy-scout rule — refactor the test you touch).
- Do NOT bulk-rewrite untouched tests; migration is incremental.

## The 3 rules

### 1. Tag the top-level test class with feature + module markers

pytest has no `describe`. Use a **test class** as the top-level group and tag it
with markers. Because `pyproject.toml` runs `--strict-markers`, the marker names
must be **registered first** (one-time setup, see "Registering tag markers" below).

```python
@pytest.mark.feature("clients")
@pytest.mark.module("client-service")
class TestCreateClient:
    ...
```

Required tags: `feature` and `module`. Optional: `flow`, `integration` (already
registered — test hits real network/db), `slow`, `live`.

### 2. Nested class = pre-condition, named "GivenX"

```python
class TestGivenAdminUserWithDraft:
    ...
class TestGivenApiReturns422OnUpdate:
    ...
```

Be specific — `TestGivenLoggedInUser` is too vague; `TestGivenUserWithoutClient`
is useful. Max nesting depth = 3 (file > class > nested-class).

### 3. Test method = "when X, then Y"

```python
def test_when_phone_is_invalid_then_returns_validation_error(self): ...
def test_when_event_has_no_client_then_refuses_and_does_not_call_google(self): ...
```

The "then" clause must describe **observable behavior** (return value, raised
exception, DB row, external call), never an implementation detail.

- ❌ `test_calls_session_add` — implementation
- ✅ `test_when_creating_client_then_persists_row_and_returns_success` — behavior

## Setup rules

### Inline `setup()` per class — no shared `@fixture` autouse for state

Prefer a small local `setup()` helper called at the top of each test over a distant
`@pytest.fixture(autouse=True)`. A reader parses one class top-down without jumping.

```python
class TestGivenValidClient:
    @staticmethod
    def setup(db):
        deps = AgentDeps(db=db, user_id=DEV_USER_ID)
        return deps

    def test_when_creating_client_then_returns_success(self, db):
        deps = self.setup(db)
        result = create_client_impl(deps, name="Maria Silva", phone="51981321543")
        assert result["success"] is True
        assert result["data"]["name"] == "Maria Silva"
```

**Exception — mock/state hygiene is allowed in a fixture.** Resetting state between
tests is isolation, not setup. Keep it small and never build domain fixtures or run
the system-under-test inside it.

### Co-located fixtures

Declare fixture data at the top of the test file. Only extract to a shared
`conftest.py` / `tests/fixtures/` if used by 2+ files. Resist preventive extraction.

### Explicit asserts, never custom assertion helpers

```python
# ✅ Self-evident
assert mock_calendar.create_event.call_args.kwargs["client_id"] == client.id
assert result["success"] is False

# ❌ Hides what's being tested
assert_client_was_created(name="Maria", with_event=True)
```

### Subtle scenarios: `# @scenario:` comment

```python
# @scenario: dual-write rollback — Postgres fails after Google write succeeds
def test_when_postgres_insert_fails_then_google_event_is_deleted(self): ...
```

Use only when the name alone doesn't convey the scenario (race, retry, compensation,
RBAC edge).

## Async tests

`asyncio_mode = "auto"` is set — just write `async def test_...`; no decorator needed.
Use `AsyncMock` for awaitables (matches existing patterns in `tests/`).

## Registering tag markers (one-time)

`--strict-markers` rejects unknown markers. Add `feature`, `module`, `flow` to the
markers list in `pyproject.toml` (`integration`, `unit`, `slow`, `live` already exist):

```toml
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
    "live: end-to-end tests against real LLM + Google (RUN_LIVE=1)",
    "feature(name): the product feature under test (e.g. clients, agenda, billing)",
    "module(name): the code module under test (e.g. client-service, calendar-tools)",
    "flow(name): the end-to-end flow under test",
]
```

Then filter by tag: `pytest -m 'feature(\"clients\")'` or `pytest -m integration`.

## Anti-patterns to refuse

- `def test_it_works` / `test_create` — meaningless, no behavior.
- Asserting only on mock call counts without asserting the observable effect.
- Class nesting deeper than 3 levels.
- Sharing state between tests via module/outer-scope mutable globals — every test independent.
- Portuguese in test names, comments, or fixtures — tests are code, code is English.

## Relationship to TDD

This skill is the **how-to-structure**; `superpowers:test-driven-development` is the
**when** (red→green→refactor). For a bugfix follow the repo's Bug-Fix TDD protocol:
failing test first (proves the bug), then fix, then green.
