# Evolution Engine

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `SANDBOX_ENGINE.md` (execution isolation),
> `AI_SYSTEM.md` (the router this module bypasses), `SECURITY_GUIDE.md`
> (approval-gate requirements before `Installer`/`GitManager.commit`),
> `MODULE_GUIDE.md` (per-file maturity table).

The Evolution Engine is JARVIS OS's self-modifying-code subsystem: it can
scan the project, plan an improvement, generate a patch via a local LLM,
statically review it, sandbox-execute it, and (pending human approval)
commit it. **This is the most mature package in the codebase** — it is the
reference standard for code quality (`CODING_STANDARDS.md`) going forward.

## Pipeline (catalog of stages)

> See "Orchestration" below for what's actually wired together and runnable
> today — this section is a catalog of every stage *class* that exists, not
> a description of one connected pipeline.

The list below is every stage *class* that exists in `app/evolution/`. It is
**not** a description of one connected pipeline that executes end-to-end —
see the Orchestration section immediately after this one for the real,
verified call graph, which uses only a subset of these stages and skips
several entirely.

```
scanner.py          ──▶ ProjectScanner: AST-walks app/, writes
                         data/evolution_report.json (files/classes/
                         functions/imports + counts)
analyzer.py          ──▶ Analyzer: file count, line count, sha256 hash of
                          all *.py under a root — a lighter-weight sibling
                          of scanner.py, not a consumer of its output
planner.py            ──▶ EvolutionPlanner: reads data/ai_prompt.txt, calls
                            OllamaProvider directly, writes
                            data/improvement_plan.md
context_builder.py     ──▶ ContextBuilder: writes data/project_tree.txt,
                             consumed by generator.py
generator.py             ──▶ CodeGenerator: prompts OllamaProvider for a
                              full replacement file, writes
                              data/generated_patch.py
reviewer.py                ──▶ PatchReviewer: strips markdown fences,
                                ast.parse() syntax check, one heuristic
                                import-usage warning, writes
                                data/review_report.txt
validator.py                 ──▶ PatchValidator: a second, independent
                                  patch-checker — strips fences, ast.parse(),
                                  and additionally checks every `app.*`
                                  import in the patch actually resolves via
                                  importlib.util.find_spec, writes
                                  data/validation_report.txt. See
                                  "Two Independent Patch Checkers" below —
                                  this overlaps with reviewer.py rather than
                                  extending it.
autofix.py                    ──▶ AutoFixer: if review found WARNING/ERROR,
                                   re-prompts Ollama with the review + patch
                                   to repair it. **Verified unreachable:**
                                   `grep -rn AutoFixer app/` finds only its
                                   own class definition — nothing in the
                                   package ever constructs it.
sandbox.py                     ──▶ Sandbox: isolated, resource-limited
                                    execution of a patch — see
                                    SANDBOX_ENGINE.md. **Verified
                                    unreachable** from `brain.py`'s actual
                                    orchestration (see below).
installer.py                    ──▶ STUB — currently just returns
                                    "Waiting for user approval." No actual
                                    file replacement happens here yet.
git_manager.py                    ──▶ GitManager: status/add_all/commit/
                                       current_branch via subprocess
rollback.py                        ──▶ RollbackManager: create_backup/
                                        restore via shutil.copytree
version.py                          ──▶ VersionManager: reads/writes
                                         data/version.json, defaults to
                                         Version(0, 6, 0) — see
                                         JARVIS_ARCHITECT.md's Version Drift
                                         section, this is a third,
                                         *actively executing* source of the
                                         "0.6.0" drift, not just a stale
                                         comment
tester.py                           ──▶ TestRunner: subprocess-runs
                                         `python -m pytest <target>`
benchmark.py                        ──▶ Benchmark: times a callable,
                                        catches exceptions as `success=False`
```

## Orchestration — what's actually wired together and runnable today

Two concrete entry points exist. Both were read in full to produce this
section; nothing here is inferred from naming conventions.

### `EvolutionManager.run()` (`manager.py`) → `EvolutionBrain.evolve()` (`brain.py`)

This is the **one real, callable pipeline** in the package
(`python -m app.evolution.manager` or `EvolutionManager().run()`). Its
actual call graph, in order:

```
ProjectScanner().scan()
EvolutionPlanner().create_plan()        # calls OllamaProvider directly
input("Choose task: ")                  # blocking interactive prompt —
                                         # picks one of 4 hardcoded
                                         # (task, target_file) pairs
CodeGenerator().generate_task(task, target)   # calls OllamaProvider directly
PatchReviewer().review(patch, target)
PatchValidator().validate(patch)
# prints "[READY]" or "[BLOCKED]" based on validator's `ok` return value
```

This chain **never calls** `analyzer.py`, `autofix.py`, `sandbox.py`,
`installer.py`, `git_manager.py`, `rollback.py`, `version.py`, `tester.py`,
or `benchmark.py`. Concretely: today, running the Evolution Engine's real
entry point can generate and statically validate a patch, but cannot
sandbox-execute it, auto-repair it, roll it back, version-bump it, test it,
benchmark it, or commit it — every stage after "validate" in the conceptual
pipeline above requires code that exists but is not yet wired in.

Also note: `EvolutionBrain.TASKS` hardcodes exactly 4 improvement targets
(`app/skills/loader.py`, `app/memory/search.py`, `app/ai/router.py`,
`app/evolution/sandbox.py`) — the Evolution Engine cannot today target an
arbitrary file, only one of these four.

### `Updater` (`updater.py`) — constructs the full pipeline, calls almost none of it

`Updater.__init__` constructs an `Analyzer`, `EvolutionPlanner`,
`CodeGenerator`, `TestRunner`, `Benchmark`, `GitManager`, `RollbackManager`,
and `VersionManager` — all eight stage objects. But its two public methods
use almost none of them:

- `status()` **is real** — it calls `self.analyzer.analyze()` and
  `self.version.info()` and returns a genuine `{version, files, lines,
  hash}` dict.
- `upgrade_requested()` **is a stub** — it does not call `self.planner`,
  `self.generator`, `self.tester`, `self.benchmark`, `self.git`, or
  `self.rollback` at all. It unconditionally returns
  `UpdateReport(success=True, message="Upgrade pipeline initialized...")`
  regardless of what those objects would actually report.

Constructing all eight dependencies in `__init__` while only using two of
them in one of two methods is a strong signal of *intended* future wiring
that was never finished — worth flagging to whoever picks this file up next
so they don't assume `Updater.upgrade_requested()` does what its name and
constructor implies.

## Two Independent Patch Checkers

`reviewer.py` (`PatchReviewer`) and `validator.py` (`PatchValidator`) both
exist to answer the same question — "is this generated patch safe to use?"
— with different, non-overlapping checks (reviewer: one hardcoded
import-usage heuristic; validator: syntax + `app.*` import resolution) and
different output files (`review_report.txt` vs. `validation_report.txt`).
Neither calls the other; `EvolutionBrain.evolve()` calls both in sequence
but never reconciles their two boolean verdicts against each other (it only
branches on the validator's `ok`, silently ignoring a `False` `syntax` from
the reviewer if the validator's independent `ast.parse()` happened to
succeed on the same code). This is the same root pattern as
`DESIGN_PRINCIPLES.md`'s weakness #1 (`CommandRouter` vs. the Cortex
pipeline) and is now cataloged there as weakness #11 — two upgrade scripts
independently building "the thing that checks the patch," neither aware of
the other.

## Key Contracts

### `CodeGenerator.generate_task(task, target_file, output="data/generated_patch.py")`
Reads the current project tree (`ContextBuilder().build()`) and the target
file's current source, builds a prompt instructing the model to "return ONLY
the complete replacement Python file" while preserving class names and
public methods, and writes the raw model output to `output`. **Note:** the
model's response is written verbatim — including any markdown code fences —
which is why `PatchReviewer` has explicit fence-stripping logic before
`ast.parse()`.

### `PatchReviewer.review(patch, original)`
Returns and persists a dict:
```python
{"syntax": bool, "imports_ok": bool, "errors": [...], "warnings": [...]}
```
Only one warning heuristic exists today (a hardcoded string check for
`"package = app.skills"` without a matching import). This is a placeholder
for a fuller static-analysis pass, not a complete review — do not treat
`review["syntax"] is True` as "this patch is safe."

### `PatchValidator.validate(patch_path="data/generated_patch.py")`
Returns `(ok: bool, report: list[str])` and persists `report` to
`data/validation_report.txt`. Strips markdown fences, `ast.parse()`s the
code, then regex-extracts every `import`/`from ... import` line and — for
any module starting with `app.` — calls `importlib.util.find_spec(mod)` to
confirm it actually resolves, failing validation if not. This is the check
that actually gates `EvolutionBrain.evolve()`'s "[READY]"/"[BLOCKED]"
verdict; `PatchReviewer`'s output is generated but not consulted for that
verdict. See "Two Independent Patch Checkers" above.

### `AutoFixer.fix(review_file, patch_file)`
Short-circuits ("Patch already passed review") if the review report contains
neither `"WARNING"` nor `"ERROR"`; otherwise re-prompts the LLM with the
review and the patch, instructing it to fix every warning/error while
keeping the same filename and public API, and overwrites `patch_file`.
**No loop/retry limit** — if the LLM's fix still fails review, nothing
currently re-invokes `AutoFixer` again. **Verified: this file is currently
unreachable** — see "Orchestration" above. `EvolutionBrain.evolve()` does
not call it, and no other file in the package does either.

### `Sandbox.run(source) -> SandboxResult`
See `SANDBOX_ENGINE.md` for the full breakdown. In short: statically
validates the source against a deny-list, and if clean, executes it in an
isolated temp directory as a subprocess with a wall-clock timeout and
RAM/CPU tracking (via `psutil` if available), then writes a report to
`data/sandbox_report.{txt,json}`. **Verified: currently unreachable** from
the one real orchestration path (`EvolutionBrain.evolve()`) — see
"Orchestration" above.

### `GitManager`
Thin, correct wrapper: every method returns a `GitResult(success, output,
error)` built from a `subprocess.run(["git", *args], capture_output=True,
text=True)` call. No commit signing, no branch protection checks, no diff
review before commit — it trusts the caller to have already gated the commit
on review/sandbox success. **Verified: currently unreachable** from
`EvolutionBrain.evolve()`; only constructed (never called) by `Updater`.

### `Installer`
Currently a two-line stub:
```python
class Installer:
    def install(self):
        return "Waiting for user approval."
```
There is **no code path today that actually writes an approved patch back
into the live `app/` tree.** This is intentional-looking (the string implies
a human-in-the-loop gate is meant to exist) but the approval mechanism
itself (where does a human say "yes"? CLI prompt? GUI button? file flag?)
is not implemented anywhere in the codebase. This is a Phase 5 design
decision, not a bug fix — flag it to the user before building it. See
`SECURITY_GUIDE.md` recommendation 2.

## Why This Module Is More Mature Than the Rest

- Comprehensive docstrings explaining intent, not just mechanics
  (`sandbox.py`'s module docstring and `SecurityValidator`'s honest
  "this is a guardrail, not a security boundary" note are exemplary).
- Explicit dataclasses for all results (`SandboxResult`, `GitResult`,
  `AnalysisResult`, `BenchmarkResult`, `RollbackResult`, `TestResult`,
  `UpdateReport`).
- Real exception handling with specific exception types
  (`except (OSError, subprocess.SubprocessError)`), not bare `except:`.
- Resource cleanup guaranteed via `try/finally` (workspace cleanup).
- Atomic file writes (`SandboxReporter._atomic_write` via `.tmp` +
  `Path.replace`).

This maturity is real but locally scoped: the individual stage classes are
well-built, while the orchestration connecting them (see above) is thin,
partial, and in places duplicated. Any future work on `app/core`,
`app/memory`, `app/cortex`, or `app/gui` should still be reviewed against
this module's per-file coding standard — but future work *on this module
itself* should prioritize wiring (Orchestration section) over further
per-file polish.

Any future work on `app/core`, `app/memory`, `app/cortex`, or `app/gui`
should be reviewed against this module's standard, not against the
lighter-weight style found elsewhere in the tree.

## Direct Coupling to Ollama

`CodeGenerator`, `AutoFixer`, **and `EvolutionPlanner`** — three files, not
two — construct `OllamaProvider()` directly rather than going through
`AIRouter`/`AIManager` (see `AI_SYSTEM.md` #2). This means the Evolution
Engine cannot currently be pointed at a different model/provider without
editing all three files.
