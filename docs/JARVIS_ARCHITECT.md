# JARVIS OS — Architect Bible

**Status:** Living document. This is the permanent source of truth for JARVIS OS.
Every future development task — human or AI-generated — must comply with this
document and the documents it links to. If a request conflicts with this Bible,
the conflict must be raised and resolved before code is written (see Phase 5
in `ROADMAP.md`).

This document was produced by static analysis of the codebase as of
commit `30fe1fb` ("rename Evolution to evolution"), version string
`0.4.0-alpha` (`app/core/config.py`), with several internal files
self-labelled `Version: 0.6.0` (see "Version drift" below).

**Revision note (2026):** this document set underwent a full
verification pass in which every claim below and in the linked documents
was checked directly against source — by importing modules, grepping for
call sites, and running the actual failure paths rather than reasoning
about them statically. That pass corrected several claims that were
directionally right but one layer off from what the code actually does
(see `MEMORY_SYSTEM.md` and `EVOLUTION_ENGINE.md` for the two largest
corrections). Nothing in this document set today is a placeholder or an
"unread — verify before use" caveat; every file referenced has been read.

---

## 1. What JARVIS OS Is

JARVIS OS is a Windows desktop AI assistant framework combining:

- A **kernel/service-registry core** (dependency injection, event bus, boot sequence)
- A **skills/plugin system** (auto-discovered command handlers)
- A **memory engine** (JSON-file-backed short/long-term memory)
- A **multi-provider AI layer** (Ollama, OpenAI, Claude, Gemini, DeepSeek)
- A **Cortex NLU pipeline** (intent detection, entity extraction, brain routing)
- An **Evolution Engine** — a self-modifying code pipeline that can scan the
  codebase, plan a change, generate a patch via a local LLM, review it,
  sandbox-execute it, and (pending approval) commit it via git
- A **voice engine** (recording, wake word, Whisper transcription — largely stubbed)
- A **desktop GUI** (customtkinter — partially stubbed)

## 2. High-Level Architecture

```
                         ┌──────────────────┐
                         │     main.py      │
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │  JarvisKernel     │  app/core/kernel.py
                         │  .boot()          │
                         └────────┬─────────┘
             ┌────────────────────┼─────────────────────┐
             │                    │                      │
   ┌─────────▼────────┐ ┌─────────▼────────┐  ┌──────────▼─────────┐
   │ ServiceRegistry   │ │   EventBus       │  │  MemoryManager       │
   │ (DI container)    │ │ (pub/sub)        │  │  (JSON persistence)  │
   └─────────┬─────────┘ └──────────────────┘  └──────────────────────┘
             │
   ┌─────────▼─────────┐        ┌──────────────────┐
   │  SkillLoader        │──────▶│  SkillManager      │
   │ (pkgutil discovery) │       │ (intent → Skill)   │
   └────────────────────┘       └──────────────────────┘

   NOT wired into the Kernel today (see §4 "Integration Gaps"):
   ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
   │ CortexPipeline      │   │ JarvisApp / GUI     │   │ AIManager / Router  │
   │ app/cortex/         │   │ app/core/app.py     │   │ app/ai/              │
   └────────────────────┘   └────────────────────┘   └────────────────────┘

   Independent subsystem, invoked out-of-band by developer/PowerShell scripts:
   ┌───────────────────────────────────────────────────────────────────────┐
   │ Evolution Engine  app/evolution/  (stage catalog — NOT all wired       │
   │ together; see EVOLUTION_ENGINE.md §Orchestration for the real graph)   │
   │                                                                         │
   │ Actually wired (EvolutionManager.run→EvolutionBrain.evolve):           │
   │   scanner → planner (LLM) → [interactive input()] → generator (LLM)    │
   │   → reviewer + validator (two independent, unreconciled checks)        │
   │                                                                         │
   │ Built but currently unreachable from that entry point:                 │
   │   analyzer, context_builder(*), autofix, sandbox, installer,           │
   │   git_manager, rollback, version, tester, benchmark                    │
   │   (* context_builder IS reachable — called by generator, not brain)    │
   └───────────────────────────────────────────────────────────────────────┘
```

## 3. Module Maturity Matrix

| Module | Maturity | Notes |
|---|---|---|
| `app/core` | Functional | Kernel, registry, event bus, logger all work. `startup.py` is empty. `app.py` is disconnected from the kernel. |
| `app/skills` | Functional | Solid ABC + template-method pattern, working auto-loader. One file (`system/info.py`) is completely empty despite being listed as a skill — see `DESIGN_PRINCIPLES.md` #12. |
| `app/memory` | **Cannot be imported** | Three chained bugs (`ImportError` → `TypeError` → `AttributeError`) — see `MEMORY_SYSTEM.md`. Several other files are stubs despite being listed as implemented in `__init__.py`'s docstring. |
| `app/cortex` | Partially implemented, unwired | Pipeline (`normalizer → intent_detector → entity_extractor → brain_selector`) is real and unit-testable. `handlers/` and `brains/` are all empty files. Not invoked by the kernel. |
| `app/ai` | Scaffolded, non-functional | Router pattern is sound; every provider except Ollama raises `NotImplementedError`. |
| `app/evolution` | **Most mature module at the file level; thin at the orchestration level** | Real error handling, dataclasses, docstrings, AST-based static analysis, resource-limited subprocess execution — reference standard for per-file code quality. But only one entry point (`EvolutionManager`/`EvolutionBrain`) actually chains any stages together, and it uses 5 of the package's 14 classes — see `EVOLUTION_ENGINE.md` §Orchestration. |
| `app/voice` | Mostly stubs | `manager.py` and `listener.py` work standalone; `vad.py`, `wakeword.py`, `recognizer.py`, `speaker.py`, `commands.py`, `config.py` are empty. |
| `app/gui` | Mostly stubs | `window.py`, `theme.py`, `sidebar.py` implemented; all page/component files empty. Not wired to the kernel. |
| `app/generator` | Functional but **incompatible with the skill runtime** | See `PLUGIN_SYSTEM.md` — generated skills do not subclass `Skill` and would not be loaded by `SkillLoader`. |
| `tests/` | Effectively absent | One manual script, no assertions, no framework. |

## 4. Integration Gaps (read before adding features)

These are structural facts about the current codebase, not opinions:

1. **`main.py` never starts the GUI.** It calls `JarvisKernel().boot()`, which
   registers services and loads skills, then returns. There is no event loop,
   no call into `app/core/app.py`, no way for a user to actually interact with
   the running kernel.
2. **The GUI never talks to the kernel.** `JarvisApp.run()` constructs a
   `JarvisWindow` directly. It never receives a `ServiceRegistry`, so the GUI
   cannot dispatch to skills, read memory, or emit events.
3. **The Cortex pipeline is not called by anything in `app/core`.**
   `CortexPipeline.process()` produces a fully-formed `CortexRequest`
   (intent, entities, brain), but nothing hands that request to `Dispatcher`
   in the current boot sequence — `Dispatcher` itself is standalone and unused.
4. **Two independent routers exist**: `app/core/router.py::CommandRouter`
   (three-bucket prefix match: automation / developer / chat) and
   `app/cortex/intent_detector.py::IntentDetector` (finer-grained intent
   enum). They overlap in responsibility and are not reconciled.
5. **`AIManager`/`AIRouter` are not used by anything else in the codebase** —
   no skill, handler, or brain currently calls into the AI layer, and the
   Evolution Engine talks to `OllamaProvider` directly instead of going
   through the router, in three separate files (`generator.py`, `autofix.py`,
   `planner.py` — see `AI_SYSTEM.md` #2).
6. **The Evolution Engine's own pipeline is itself only partially wired.**
   `EvolutionBrain.evolve()` is the one real entry point, and it skips
   `analyzer`, `autofix`, `sandbox`, `installer`, `git_manager`, `rollback`,
   `version`, `tester`, and `benchmark` entirely — see
   `EVOLUTION_ENGINE.md` §Orchestration. This is the same class of gap as
   items 1–4 above, just one level deeper inside a single module rather than
   between modules.

None of this is inherently wrong for a `0.4.0-alpha` project — but it means
**"wire module X into the kernel" is a prerequisite for most future feature
work**, not an optional nice-to-have. Treat integration gaps as tracked debt
(`ROADMAP.md`), not as implicit scope for unrelated tasks.

## 5. Version Drift

- `app/core/config.py`: `VERSION = "0.4.0-alpha"`
- `app/memory/*.py` file headers: `Version: 0.6.0`
- Git history: `"JARVIS v0.6 Evolution + AI Foundation"`
- **`app/evolution/version.py`'s `VersionManager`: actively writes
  `Version(0, 6, 0)` to `data/version.json` as its default, the first time
  it runs.** This is the only one of the four that is *live code*, not a
  stale comment or a historical commit message — every time
  `VersionManager()` is constructed against a missing `data/version.json`
  (e.g. via `Updater.status()`), it re-asserts "0.6.0" as current fact. See
  `EVOLUTION_ENGINE.md`'s pipeline catalog entry for `version.py`.

There is one authoritative version string (`Config.VERSION`) and it is stale.
Going forward, `Config.VERSION` is the single source of truth; per-file
`Version:` header comments must be removed (see `CODING_STANDARDS.md` —
unnecessary comments are disallowed), and `VersionManager`'s default should
either read from `Config.VERSION` or be removed in favor of it, so there is
exactly one place a version number can be wrong.

## 6. Document Map

| Document | Covers |
|---|---|
| `PROJECT_STRUCTURE.md` | Full folder/file inventory and purpose |
| `CODING_STANDARDS.md` | Mandatory style, typing, and formatting rules |
| `DESIGN_PRINCIPLES.md` | SOLID/Clean Architecture application; the master numbered weakness list (12 items) that every other doc's fixes trace back to |
| `MODULE_GUIDE.md` | Per-module, per-class API reference and verified status — every row confirmed against source, no unread files remain |
| `AI_SYSTEM.md` | AIManager/AIRouter/providers, and the three Evolution Engine files that bypass them |
| `MEMORY_SYSTEM.md` | Memory engine, including the verified three-link import→construct→call failure chain |
| `EVOLUTION_ENGINE.md` | Self-modifying code pipeline — full stage catalog plus the verified orchestration section showing which stages are actually wired together and callable today |
| `SANDBOX_ENGINE.md` | Sandbox execution model and its real security boundary |
| `PLUGIN_SYSTEM.md` | Skill ABC, loader, the generator incompatibility, and per-skill verification status |
| `GUI_GUIDELINES.md` | customtkinter theme, layout, component inventory |
| `TESTING_GUIDE.md` | Test strategy (none exists today) |
| `SECURITY_GUIDE.md` | Secrets, sandboxing limits, subprocess whitelisting; `.env` git-history check (verified clean) |
| `LOGGING_GUIDE.md` | Logging conventions and the current inconsistency |
| `ROADMAP.md` | Current project status and long-term vision, both derived from this analysis |

Every document above cross-references the others where its claims depend on
or extend a claim made elsewhere — follow the `See X.md` pointers rather
than assuming a single doc is self-contained.

## 7. Governing Rule for All Future Work

Any Claude session (or human) doing development on JARVIS OS must:

1. Read `JARVIS_ARCHITECT.md` (this file) and the relevant module doc first.
2. If the requested change conflicts with an established pattern in
   `DESIGN_PRINCIPLES.md` or `CODING_STANDARDS.md`, **stop, explain the
   conflict, and propose an alternative** before writing code.
3. Never silently "fix" unrelated integration gaps as a side effect of an
   unrelated task — file them as roadmap items instead, unless the user asks
   for the fix directly.
4. Update the relevant doc in this folder in the same change that alters the
   architecture it describes.
5. When updating any doc, verify the specific claim against source directly
   (import it, grep for it, run it) rather than trusting an existing doc's
   self-description — this document set has already had one round of
   corrections (2026) where claims that sounded plausible on inspection
   turned out to be one layer off from what actually executes (see
   `MEMORY_SYSTEM.md`'s three-link chain and `EVOLUTION_ENGINE.md`'s
   Orchestration section for two examples). Treat every doc as a hypothesis
   to be checked, not a source of truth in its own right — the source code
   is the only source of truth; these documents are a maintained model of
   it that can drift and must be re-verified whenever touched.
