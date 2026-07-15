# Testing Guide

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `MEMORY_SYSTEM.md` (the three-link chain
> priority 1 below is built to catch), `SANDBOX_ENGINE.md` (priority 3/4).

## Current State: No Test Suite Exists

`tests/_storage.py` is the only file in `tests/`:

```python
from app.memory.storage import MemoryStorage

db = MemoryStorage("history.json")
db.set("user", "Muhammed")
print(db.get("user"))
```

This is a manual smoke-check script, not a test:
- No test framework (no `pytest`/`unittest` import, not in `requirements.txt`).
- No assertions — it prints a value for a human to eyeball.
- Filename prefixed with `_`, suggesting it's excluded from whatever
  discovery mechanism might otherwise be intended (or just informal).
- Does not exercise `MemoryManager` at all, which is why the three-link
  import→construct→call bug chain in `MEMORY_SYSTEM.md` shipped unnoticed —
  a test that only asserted "construction succeeds" would still have missed
  the third link (`save_item`), so priority 1 below is written to assert on
  a full `remember()` round-trip, not just construction.

There is no CI configuration (no `.github/workflows`, no `tox.ini`, no
`pytest.ini`/`pyproject.toml` test config) found in the project tree.

## Required Going Forward

1. Add `pytest` to `requirements.txt` (currently absent entirely).
2. Every new `Skill`, provider, or Evolution Engine stage must ship with at
   least one test that exercises its public contract, in the same change
   that introduces it (not "added later").
3. Structure: mirror `app/` under `tests/`, e.g. `tests/skills/test_launcher.py`
   for `app/skills/application/launcher.py`.
4. Tests must not depend on the working directory being the project root
   in an unstated way, and must not write to `data/`/`logs/` without cleaning
   up (use `tmp_path`/`tmp_path_factory` fixtures — `MemoryStorage`'s
   filename-based construction makes this straightforward: point it at a
   temp directory in tests rather than the real `data/memory/`).

## Suggested Coverage Priorities (highest value first)

| Priority | Target | What to verify |
|---|---|---|
| 1 | `MemoryManager().remember(...)` end-to-end | Currently fails at `import app.memory` itself (see `MEMORY_SYSTEM.md`'s three-link chain). Write a test that imports, constructs, and calls `remember()` — not just construction — so all three links (`ImportError` → `TypeError` → `AttributeError`) are caught by one test, watch it fail, then fix all three in one change. |
| 2 | `SkillLoader.load()` | Assert that every `Skill` subclass under `app/skills/` gets registered, and — critically — that `app/skills/generated/calculator.py`'s current form is *not* silently expected to register (document the gap with a test that would start passing once `PLUGIN_SYSTEM.md`'s fix lands). |
| 3 | `SecurityValidator.validate()` (`app/evolution/sandbox.py`) | Table-test every entry in `BLOCKED_IMPORTS`/`BLOCKED_CALLS`/`BLOCKED_ATTRIBUTES`, plus the alias-evasion case (`from os import system as run`) already handled in code — regression-proof this before anyone edits the deny-list. |
| 4 | `Sandbox.run()` end-to-end | A trivial `print("ok")` script succeeds; a script importing `socket` is blocked with the expected violation message; a script that sleeps past the timeout is killed and `timed_out=True`. |
| 5 | `IntentDetector.detect()` / `Normalizer.process()` | Pure functions, cheap to test exhaustively — table-test every `Intent` branch and wake-word/synonym case. |
| 6 | `PatchReviewer.review()` vs. `PatchValidator.validate()` | Valid syntax passes both; invalid syntax produces the expected error string from each; markdown-fenced input is correctly stripped before parsing by both. **Also test that a patch each one disagrees about** (e.g. reviewer warns, validator's import check passes) surfaces as a visible conflict rather than being silently resolved in the validator's favor — see `DESIGN_PRINCIPLES.md` #11 and `EVOLUTION_ENGINE.md` §"Two Independent Patch Checkers". |
| 7 | `ServiceRegistry` / `EventBus` | Duplicate registration raises; missing-key `get()` raises; `publish()` calls all subscribed callbacks with the right args; `unsubscribe` actually stops delivery. |
| 8 | `EvolutionBrain.evolve()` orchestration | Assert exactly which stage classes get called (scanner, planner, generator, reviewer, validator) and which don't (analyzer, autofix, sandbox, installer, git_manager, rollback, version, tester, benchmark) — a regression test here would immediately flag it if a future change silently wires in (or accidentally drops) a stage, keeping `EVOLUTION_ENGINE.md` §Orchestration accurate without a manual doc re-audit. |

## What NOT to Do

- Do not write tests that mock away the exact bug you're supposed to be
  catching (e.g. a `MemoryManager` test that manually passes a filename to
  a mocked `MemoryStorage` instead of calling `MemoryManager()` the way the
  kernel actually does).
- Do not add tests that require a running Ollama daemon, network access, or
  real provider API keys to pass in CI — `OllamaProvider`/AI provider tests
  should mock the network boundary (`ollama.chat`, the SDK client) rather
  than hitting a real service.
- Do not test `customtkinter` GUI rendering pixel-by-pixel — test the
  data/state a page would render (once pages take injected services per
  `GUI_GUIDELINES.md`), not the widget tree.

## Target: A Runnable `pytest` Command

Once the above lands, `pytest` from the project root (with `.venv` activated)
should run the full suite with no network access and no manual setup beyond
`pip install -r requirements.txt`. This is the acceptance bar for "testable"
in `CODING_STANDARDS.md`.
