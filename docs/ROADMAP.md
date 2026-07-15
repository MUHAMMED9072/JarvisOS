# Roadmap

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. This document has two halves: **Current Project
> Status** (where the code actually is today, verified against source) and
> **Long-Term Vision** (where it's headed and in what order). The
> prioritized backlog that follows is derived directly from every other
> document in this Bible — each item links back to the doc with the full
> analysis. Nothing here should be started without confirming scope with the
> user first, per `JARVIS_ARCHITECT.md` §7.

---

## Part 1 — Current Project Status

**Version:** `0.4.0-alpha` (`Config.VERSION`) — though three other places in
the codebase claim `0.6.0`; see `JARVIS_ARCHITECT.md` §5 Version Drift.

**Can it boot?** No. `import app.memory` fails immediately (`ImportError` on
`MemoryItem`), and `JarvisKernel.__init__` imports `app.memory`
unconditionally. See `MEMORY_SYSTEM.md`.

**What works today, in isolation, if you import it directly:**
- `app/core`: registry, event bus, logger, config, both routers.
- `app/cortex`: the full normalize → intent → entities → brain-selection
  pipeline (`CortexPipeline`), fully unit-testable.
- `app/skills`: the ABC/loader/manager triad, plus 5 real skills
  (`ApplicationLauncher`, `MemoryRecallSkill`, `FallbackSkill`,
  `BrowserSearch`, `ChatSkill`) — all correctly loadable.
- `app/ai`: `OllamaProvider` (the only non-stub provider); `AIRouter`/
  `AIManager`'s dispatch logic (has nothing pointed at it in practice).
- `app/evolution`: every individual stage class works; one real orchestrated
  path exists (`EvolutionManager.run()` → `EvolutionBrain.evolve()` — see
  `EVOLUTION_ENGINE.md` §Orchestration) covering 5 of 14 classes
  (scanner, planner, generator, reviewer, validator).
- `app/voice`: `VoiceListener` (record) and `WhisperProvider` (transcribe)
  work standalone, not connected to each other.
- `app/gui`: `JarvisWindow`/`Sidebar`/`theme.py` render, standalone, with no
  data behind them.

**What's connected to what:** almost nothing. `main.py` boots the kernel and
exits — no GUI, no event loop. The GUI never receives a `ServiceRegistry`.
The Cortex pipeline and its `Dispatcher` are never instantiated by the
kernel. The Evolution Engine's one real pipeline is invoked out-of-band
(`python -m app.evolution.manager`), not from the kernel. See
`JARVIS_ARCHITECT.md` §4 for the full integration-gap list (6 items).

**What's a complete no-op today:** `app/cortex/handlers/*.py`,
`app/cortex/brains/*.py`, `app/voice/{vad,wakeword,recognizer,speaker,
commands,config}.py`, `app/gui/pages/*.py` and most `app/gui/components/*.py`,
`app/skills/system/info.py` (0 bytes), `app/memory/{context,knowledge,
preferences,projects,search}.py` (malformed-docstring-only), `app/evolution/
installer.py` (2-line stub), 4 of 5 AI providers.

**Security posture:** sound where it exists (`ApplicationLauncher`'s
allow-list, `Sandbox`'s deny-list + resource limits), absent where it
doesn't (no approval gate for `Installer`, no OS-level sandbox isolation).
`.env` is verified never committed and correctly gitignored — see
`SECURITY_GUIDE.md`.

**Test coverage:** effectively zero — one 4-line manual script with no
assertions, no `pytest` in `requirements.txt`, no CI config anywhere in the
tree.

---

## Part 2 — Long-Term Vision

The end state this roadmap is steering toward, in priority order, is:

1. **A JARVIS OS that boots and does one thing end-to-end**: a typed or
   spoken command reaches `CortexPipeline`, resolves to a `Skill` via
   `Dispatcher`, executes against real `ServiceRegistry` state (memory,
   event bus), and the result is visible in the GUI. Every P0/P1 item below
   exists to make this single path real; nothing past P1 matters until it
   is.
2. **A single, coherent "text/voice → action" routing layer**, not two
   competing ones (`CommandRouter` vs. `IntentDetector`) — see
   `DESIGN_PRINCIPLES.md` #1.
3. **An AI layer that's actually a layer**: every LLM call — chat, brain
   selection, and all three Evolution Engine call sites — goes through
   `AIRouter`/`AIManager` against a defined `AIProvider` Protocol, with at
   least one more real provider implemented beyond Ollama, so "JARVIS" isn't
   synonymous with "whatever's running in Ollama locally."
4. **An Evolution Engine that is trustworthy specifically because it's
   fully wired *and* gated**, not because any individual stage is
   well-written in isolation. That means: `EvolutionBrain.evolve()`
   actually reaches `sandbox.py` before anything touches disk,
   `autofix.py` is reachable and loop-limited, `reviewer.py` and
   `validator.py` are reconciled into one verdict, and `installer.py`
   has a real, documented human-approval mechanism before it does anything
   beyond returning a string. Self-modification is the project's most
   distinctive and most dangerous feature — it should be the *last*
   subsystem to get a shortcut taken on it, not the first, notwithstanding
   that it's currently the best-written code in the repo at the
   individual-file level.
5. **A codebase that no longer bears the scars of 22 undocumented
   PowerShell upgrade scripts** — one coding standard, one router, one
   patch-checker, one version string, consistently applied, with the
   scripts themselves replaced by a tracked, reviewable change mechanism.
6. **A real test suite** that would catch the next `MemoryManager`-shaped
   bug before it ships, not after — see `TESTING_GUIDE.md`.
7. **Voice and GUI as equally-first-class front ends** to the same
   kernel/skill/memory core, rather than the GUI-only framing the current
   `app/core/app.py` implies.

Everything below this line is the concrete, ordered backlog for getting
from today's state to that vision.

---

## P0 — Blocking (the app cannot boot correctly today)

1a. **Fix the `MemoryItem` import.** `app/memory/manager.py` imports
   `MemoryItem` from `.models`, but `models.py` only defines `MemoryRecord`.
   This is the *first* thing that fails — an `ImportError` at import time,
   before `MemoryManager` is ever constructed. See `MEMORY_SYSTEM.md`
   Link 1. Must be fixed before 1b/1c are even reachable to test.

1b. **Fix `MemoryManager`/`MemoryStorage` constructor mismatch.**
   `MemoryStorage.__init__` requires a `filename`; `MemoryManager.__init__`
   calls it with none. See `MEMORY_SYSTEM.md` Link 2.

1c. **Fix `MemoryManager.remember()`'s call to `self.storage.save_item()`,**
   a method `MemoryStorage` does not define. See `MEMORY_SYSTEM.md` Link 3.
   All three of 1a/1b/1c must land in the *same* change — fixing any subset
   just moves the crash one line deeper without making memory usable.

2. **Fix `MemoryHistory` list/dict contract mismatch.** Even once #1 is
   fixed, `get_recent`/`search`/`last_user_message`/`last_assistant_message`
   assume a list-shaped store; `MemoryStorage.load()` returns a dict. Must
   be fixed together with #1, not independently.

## P1 — Structural Integration (needed before most feature work is meaningful)

3. **Wire `CortexPipeline`/`Dispatcher` into `JarvisKernel`.** Currently
   nothing calls them; a text command has no path from `main.py` to a
   `Skill` executing.
4. **Wire `JarvisApp`/`JarvisWindow` to receive the `ServiceRegistry`.**
   The GUI cannot currently read memory, dispatch to skills, or listen on
   the event bus.
5. **Reconcile `app/core/router.py::CommandRouter` and
   `app/cortex/intent_detector.py::IntentDetector`.** Pick one owner for
   "text → routed action" (recommendation: `app/cortex`, since it's the
   finer-grained and more actively developed of the two) and remove the
   other, or explicitly document why both exist.
6. **Fix `SkillGenerator`/`SKILL_TEMPLATE` to produce real `Skill`
   subclasses.** See `PLUGIN_SYSTEM.md` — generated skills are currently
   invisible to `SkillLoader`.
7. **Have `SkillInstaller.install()` actually register the generated skill**
   with `SkillManager`, not just `importlib.import_module` it.
8. **Wire the rest of the Evolution Engine's own pipeline together.**
   `EvolutionBrain.evolve()` currently reaches only 5 of 14 stage classes
   (scanner, planner, generator, reviewer, validator) — `analyzer`,
   `autofix`, `sandbox`, `installer`, `git_manager`, `rollback`, `version`,
   `tester`, and `benchmark` are all fully implemented but unreachable from
   the one real entry point. See `EVOLUTION_ENGINE.md` §Orchestration.
   **This is P1, not P2 or P3, specifically because `sandbox.py` being
   unreachable means generated patches are currently validated only by
   static AST/import checks, never actually executed in isolation before a
   human would see them** — closing this gap is a security-relevant
   integration fix, not a nice-to-have. Do this before #21 (the
   `Installer` approval mechanism) — an approval gate is meaningless if the
   thing it's gating was never sandboxed in the first place.
9. **Reconcile `reviewer.py` (`PatchReviewer`) and `validator.py`
   (`PatchValidator`).** They independently check "is this patch safe?"
   with non-overlapping logic and separate report files, and
   `EvolutionBrain.evolve()` only consults one of the two verdicts today.
   Either merge them into one contract or require both to agree before
   printing "[READY]". See `DESIGN_PRINCIPLES.md` #11,
   `EVOLUTION_ENGINE.md` §"Two Independent Patch Checkers".

## P2 — Correctness & Consistency

10. **Sync version metadata — now three drift sources, not two.**
    `Config.VERSION = "0.4.0-alpha"` vs. `Version: 0.6.0` headers in
    `app/memory/*.py` vs. git history saying "v0.6" vs.
    `VersionManager`'s live default of `Version(0, 6, 0)` written to
    `data/version.json` on first run (`app/evolution/version.py` — this one
    is *executing code*, not a comment, so it actively re-asserts "0.6.0"
    every time `Updater.status()` runs against a fresh `data/` directory).
    Pick `Config.VERSION` as sole source of truth; remove per-file version
    comments (`CODING_STANDARDS.md`) and have `VersionManager` read its
    default from `Config.VERSION` instead of a hardcoded tuple. See
    `JARVIS_ARCHITECT.md` §5.
11. **Route Evolution Engine LLM calls through `AIRouter`/`AIManager`**
    instead of `CodeGenerator`, `AutoFixer`, **and `EvolutionPlanner`** (three
    files, not two — verified via `grep -rn OllamaProvider app/evolution/`)
    constructing `OllamaProvider()` directly (`AI_SYSTEM.md` #2).
12. **Define an `AIProvider` Protocol** and type `AIRouter.providers`
    against it (`AI_SYSTEM.md` #1).
13. **Implement the four stubbed AI providers** (OpenAI, Claude, Gemini,
    DeepSeek) — currently all raise `NotImplementedError`. Do this only
    after #12, so each implementation is written against a defined contract.
14. **Implement or remove `app/skills/system/info.py`.** Verified 0 bytes —
    not a stub with a `NotImplementedError`, an entirely empty file
    incorrectly listed as an existing skill in prior documentation passes.
    See `DESIGN_PRINCIPLES.md` #12. If implemented, `intent="system_info"`
    matches the naming convention of the two working skills
    (`search_web`, `chat`).
15. **Reconcile `logging.getLogger(__name__)` usage in
    `app/evolution/sandbox.py`** to go through `JarvisLogger`
    (`LOGGING_GUIDE.md`) — as an isolated, carefully-tested change given how
    stable and well-tested that file otherwise is.
16. **Wire `Config.LOG_LEVEL` into `JarvisLogger.setup()`** instead of the
    hardcoded `logging.INFO`.
17. **Remove the module-level `event_bus` singleton** in
    `app/core/event_bus.py`; require everything to go through
    `ServiceRegistry.get("event_bus")` (`DESIGN_PRINCIPLES.md` #5).
18. **Make `Config.ROOT` package-relative** (`Path(__file__).resolve()...`)
    instead of `Path.cwd()`, matching the pattern `sandbox.py` already uses
    correctly for `PROJECT_ROOT` (`DESIGN_PRINCIPLES.md` #8).
19. **Fix `requirements.txt`**: remove the duplicate `psutil` line; add
    missing runtime dependencies actually imported by the codebase
    (`ollama`, `faster-whisper`, `sounddevice`, `soundfile`, and whichever
    official SDKs get used once #13 lands); add `pytest` for
    `TESTING_GUIDE.md`.
20. **Normalize line endings** (currently a CRLF/LF mix) via
    `.gitattributes`.

## P3 — New Capability (only after P0–P2, and only on explicit request)

21. Implement `app/cortex/brains/{fast,smart,deep}_brain.py` and
    `app/cortex/handlers/*.py` — currently all empty files with no defined
    contract yet. Define the contract (likely: takes a `CortexRequest`,
    returns a `CortexResponse`, possibly calling into `AIManager`) before
    writing implementations.
22. Implement `app/voice/{vad,wakeword,recognizer,speaker,commands,config}.py`
    and connect `VoiceListener` → `WhisperProvider` → `VoiceManager` into an
    actual listen-transcribe-route loop.
23. Implement `app/gui/pages/*.py` and `app/gui/components/{status_card,
    statusbar,topbar}.py`, and wire `Sidebar` button click handlers to real
    navigation (this depends on P1 item #4).
24. Design and implement a real approval mechanism for
    `app/evolution/installer.py`, gated explicitly on user/product decision
    about what "approval" means (`SECURITY_GUIDE.md`). Depends on P1 #8 —
    an approval UI in front of an unsandboxed patch doesn't buy much safety.
25. Build the pytest suite described in `TESTING_GUIDE.md`, starting with
    the P0 regression tests (which should be written *first*, before the
    P0 fixes, so they fail red and then pass green).
26. Replace the ad hoc `upgrade_*.ps1` script workflow with a tracked,
    reviewable migration/changelog mechanism — the current 22 PowerShell
    scripts at the project root are undocumented, unversioned relative to
    each other, and are the most likely explanation for the inconsistent
    code quality observed across modules (`DESIGN_PRINCIPLES.md` #1).

## Already Resolved (verified, no action needed)

- **`.env` secret exposure risk.** `git log --all --full-history -- .env`
  returns zero commits; `.env` is not tracked. Verified clean — see
  `SECURITY_GUIDE.md`. Re-check periodically, but no remediation is needed
  today.

## Explicitly Out of Scope Unless Requested

- Expanding `SecurityValidator`'s deny-list indefinitely as a substitute for
  real OS-level sandboxing (`SANDBOX_ENGINE.md`).
- Making `ApplicationLauncher` accept arbitrary paths "for flexibility"
  (`SECURITY_GUIDE.md`) — this would reintroduce arbitrary command execution.
- Auto-committing Evolution Engine patches without a human approval step
  actually being implemented and agreed upon first, and without P1 #8
  (sandbox reachability) landing first.
