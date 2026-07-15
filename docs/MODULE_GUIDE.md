# Module Guide

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index.

Quick reference for every implemented class. "Status" reflects working code
today, not intended design. Every row in this document has now been
verified directly against source (no "not read in this pass" placeholders
remain as of this revision). See the dedicated docs (`AI_SYSTEM.md`,
`MEMORY_SYSTEM.md`, `EVOLUTION_ENGINE.md`, `SANDBOX_ENGINE.md`,
`PLUGIN_SYSTEM.md`, `GUI_GUIDELINES.md`) for the deep dives referenced below.

## app.core

| Class | File | Responsibility | Status |
|---|---|---|---|
| `JarvisKernel` | `kernel.py` | Boot sequence: registers `skill_manager`, `event_bus`, `memory` into the registry, then loads skills. | **Cannot boot** — importing `app.memory` (a prerequisite of this file) fails before `MemoryManager()` is ever reached; see `MEMORY_SYSTEM.md`'s three-link chain. |
| `ServiceRegistry` | `registry.py` | `register(name, service)` / `get(name)` / `exists` / `remove` / `list_services`. Raises on duplicate register or missing get. | Working, minimal, good. |
| `EventBus` | `event_bus.py` | `subscribe`/`unsubscribe`/`publish` by event name string. | Working. Also exports a module-level singleton — do not use it (see `DESIGN_PRINCIPLES.md` #5). |
| `Config` | `config.py` | Static class of paths and constants (`APP_NAME`, `VERSION`, `ROOT`, `*_DIR`, `APPLICATIONS`, etc.). | Working but Windows-only paths; `ROOT` is CWD-relative. |
| `JarvisLogger` | `logger.py` | Classmethod-only wrapper around `logging.basicConfig` + `info/warning/error/debug`. Lazy-initializes on first call. | Working, should be the only logging entry point (not always is — see `LOGGING_GUIDE.md`). |
| `CommandRouter` | `router.py` | Prefix-keyword based `RouteResult(CommandType, text)`. | Working in isolation; overlapping responsibility with `app.cortex` (see `DESIGN_PRINCIPLES.md` #1). |
| `JarvisApp` | `app.py` | `run()` constructs `JarvisWindow` and calls `mainloop()`. | Working standalone; never invoked by `main.py`; has no registry access. |

## app.cortex

| Class | File | Responsibility | Status |
|---|---|---|---|
| `CortexPipeline` | `pipeline.py` | Orchestrates input → normalize → intent → entities → brain selection into a filled `CortexRequest`. | Working, unit-testable, unused by the kernel. |
| `InputManager` | `input_manager.py` | Wraps raw text + source into a `CortexRequest`. | Working. |
| `Normalizer` | `normalizer.py` | Strips wake words, punctuation; maps synonyms (`launch/start/run/execute` → `open`). | Working. |
| `IntentDetector` | `intent_detector.py` | Keyword/phrase match → `(Intent, confidence)`. Six intents defined. | Working but simplistic (substring/prefix match only, no ML/embedding backing). |
| `EntityExtractor` | `entity_extractor.py` | Naive whitespace-split slot filling per intent. | Working for the 3 intents it handles; returns `{}` otherwise. |
| `BrainSelector` | `brain_selector.py` | `Intent` → `BrainType` (fast/smart/deep). | Working, but `app.cortex.brains.*` (the actual brain implementations) are all empty files, so the selection has nowhere to go yet. |
| `Dispatcher` | `dispatcher.py` | Given a filled request, stores it in memory, updates session context, resolves and executes a `Skill`. | Working in isolation; depends on `ServiceRegistry` having `skill_manager` and `memory` already registered; never instantiated by the kernel today. |
| `Intent`, `BrainType`, `CortexRequest`, `CortexResponse` | `models.py`/`intent_detector.py` | Enums/dataclasses. | Working. |
| `context.py`, `handlers/*.py`, `brains/*.py` | — | Empty files. | Not implemented. |

## app.ai

| Class | File | Responsibility | Status |
|---|---|---|---|
| `AIManager` | `manager.py` | Facade: `ask(provider, prompt)` → `AIRouter.ask`. | Working facade over a non-functional router. |
| `AIRouter` | `router.py` | `ask(provider, prompt)` → looks up provider by name, calls `.generate(prompt)`. | Working dispatch logic; 4 of 5 providers raise `NotImplementedError`. |
| `OllamaProvider` | `providers/ollama.py` | Calls local Ollama via the `ollama` package, model `qwen2.5-coder` by default. | **Only functional provider.** Used directly (not via the router) by `app/evolution/generator.py`, `autofix.py` (unreachable — see below), and `planner.py` — three files, not two. |
| `OpenAIProvider`, `ClaudeProvider`, `GeminiProvider`, `DeepSeekProvider` | `providers/*.py` | Read an API key from `.env` via `python-dotenv`; raise `RuntimeError` if missing, else `NotImplementedError("Implement SDK call for ...")`. | Scaffolded only. |

## app.memory

See `MEMORY_SYSTEM.md` for the full contract and the three-link failure chain.

| Class | File | Responsibility | Status |
|---|---|---|---|
| `MemoryManager` | `manager.py` | Public facade: `remember`, `set_context`, `get_recent`, `search`, `get_session_messages`, `get_last_application`, `clear`. | **Cannot even be imported** — see `MEMORY_SYSTEM.md`'s three-link chain (`ImportError` on `MemoryItem` → `TypeError` on `MemoryStorage()` → `AttributeError` on `save_item`). |
| `MemoryStorage` | `storage.py` | JSON file CRUD keyed by an explicit `filename` argument, rooted at `data/memory/`. | Working in isolation (see `tests/_storage.py`); incompatible with how `MemoryManager` calls it. |
| `SessionMemory` | `session.py` | In-process `deque(maxlen=20)` of recent turns + last intent/entities/application/skill. | Working. |
| `MemoryHistory` | `history.py` | `get_all`/`get_recent`/`search`/`last_user_message`/`last_assistant_message` — all assume `storage.load()` returns a **list**. | Working only if paired with a storage backend that returns a list; `MemoryStorage.load()` returns a **dict**. This is `MEMORY_SYSTEM.md`'s "Secondary Bug" — separate from, and in addition to, the three-link chain above. |
| `MemoryRecord` | `models.py` | `key`/`value`/`created`/`updated` dataclass with `to_dict`/`from_dict`. | Working, unused by `MemoryStorage` (which stores raw dicts, not `MemoryRecord` instances). |
| `context.py`, `knowledge.py`, `preferences.py`, `projects.py`, `search.py` | — | Files contain only a malformed docstring (`\"\"\"...\"\"\"` literally escaped, so it's not even a valid docstring) — no code. | Not implemented, despite being listed in `app/memory/__init__.py`'s module docstring as existing subsystems. |

## app.skills

See `PLUGIN_SYSTEM.md` for the full contract.

| Class | File | Responsibility | Status |
|---|---|---|---|
| `Skill` (ABC) | `base.py` | Template method `execute()` (timing + exception safety) wraps abstract `run(request)`. Class attrs: `name`, `intent`, `version`, `description`, `author`. `setup(registry)` injects `memory`/`event_bus`/`skill_manager`. | Working, well-designed. |
| `SkillManager` | `manager.py` | `register(skill)` keyed by `skill.intent`; `get(intent)` with `FallbackSkill` default; `all_skills()`. | Working. |
| `SkillLoader` | `loader.py` | `pkgutil.walk_packages` over `app.skills`, imports every submodule, reflects for `Skill` subclasses, injects registry, registers with manager. Skips `base`/`manager`/`loader`/`result` modules by suffix match. | Working — this is what silently excludes non-`Skill` classes like `CalculatorSkill`. |
| `SkillResult` | `result.py` | `success`/`message`/`data`/`execution_time`/`skill` dataclass with `.ok()`/`.fail()` constructors. | Working. |
| `ApplicationLauncher` | `application/launcher.py` | Whitelisted (`Config.APPLICATIONS`) subprocess app launch. `intent = "open_application"`. | Working, good security pattern. |
| `MemoryRecallSkill` | `memory_recall/skill.py` | Reads `self.memory.get_last_application()`. `intent = "memory_recall"`. | Working (once the memory bug is fixed). |
| `FallbackSkill` | `unknown/fallback.py` | Default "I don't know how to handle that" response. `intent = "unknown"`. | Working. |
| `CalculatorSkill` | `generated/calculator.py` | Regex-based arithmetic parser. Does **not** subclass `Skill`, has no `intent`. | Functional as a plain class if imported directly; invisible to `SkillLoader`/`SkillManager`. |
| `BrowserSearch` | `browser/search.py` | Correctly subclasses `Skill`. `intent = "search_web"`. Reads `request.entities["query"]`, returns a canned "Searching for: {query}" — no actual browser/search integration yet. | **Verified.** Working, loadable, contract-compliant. |
| `ChatSkill` | `ai/chat.py` | Correctly subclasses `Skill`. `intent = "chat"`. Always returns a canned "Reasoning Brain will be connected later." — not wired to `AIRouter`/`AIManager`. | **Verified.** Working, loadable, contract-compliant. |
| — | `system/info.py` | **Verified: the file is 0 bytes.** No class, no code — not a stub with a `NotImplementedError`, an entirely empty file. | Not implemented. Do not reference "the system info skill" as if it exists — see `DESIGN_PRINCIPLES.md` #12. |

## app.generator

| Class | File | Responsibility | Status |
|---|---|---|---|
| `SkillGenerator` | `skill_generator.py` | Renders `SKILL_TEMPLATE` with a class name derived from `skill_name`, writes to `app/skills/generated/`. | Working as a code-writer; output is not `Skill`-loader-compatible (see `PLUGIN_SYSTEM.md`). |
| `SKILL_TEMPLATE` | `templates.py` | Plain-class template: `class {class_name}: name = ...; def run(self, **kwargs): ...`. | Needs to be rewritten to subclass `Skill` and implement `run(self, request) -> SkillResult`. |
| `SkillInstaller` | `installer.py` | `importlib.import_module(module_name)` — imports but does not register anything. | Minimal; not integrated with `SkillManager.register`. |

## app.voice

| Class | File | Responsibility | Status |
|---|---|---|---|
| `VoiceManager` | `manager.py` | `start()`/`stop()`/`is_running()` — flips an `enabled` bool and prints. | Working but does nothing beyond the flag. |
| `VoiceListener` | `listener.py` | Fixed-duration `sounddevice` recording to a `.wav` file. | Working standalone. |
| `WhisperProvider` | `providers/whisper_provider.py` | Loads a `faster_whisper.WhisperModel` (CPU, int8) and transcribes a file. | Working standalone; not wired to `VoiceListener` or `VoiceManager`. |
| `recognizer.py`, `speaker.py`, `vad.py`, `wakeword.py`, `commands.py`, `config.py` | — | Empty files. | Not implemented. |

## app.gui

See `GUI_GUIDELINES.md`.

| Class | File | Responsibility | Status |
|---|---|---|---|
| `JarvisWindow` | `window.py` | Main `customtkinter` window (224 lines). | Working standalone; not connected to `ServiceRegistry`. |
| `Sidebar` | `components/sidebar.py` | Nav buttons: Dashboard, AI Chat, Voice, Memory, Automation, Plugins, Settings. Buttons are created but not wired to click handlers. | Partially working (renders; no navigation logic). |
| `theme.py` | — | `COLORS` dict, `APP_TITLE`, `WINDOW_WIDTH/HEIGHT`, `SIDEBAR_WIDTH` design tokens. | Working, well-scoped. |
| `status_card.py`, `statusbar.py`, `topbar.py`, `pages/*.py` | — | Empty files. | Not implemented. |

## app.evolution

Full detail in `EVOLUTION_ENGINE.md` and `SANDBOX_ENGINE.md`.

| Class | File | Status |
|---|---|---|
| `Sandbox`, `SecurityValidator`, `WorkspaceManager`, `ProcessRunner`, `SandboxReporter` | `sandbox.py` | Fully implemented, production-quality. Reference standard for the rest of the codebase. **Verified unreachable from `EvolutionBrain.evolve()`** — not called by the one real orchestration entry point (see `EVOLUTION_ENGINE.md` §Orchestration). |
| `GitManager` | `git_manager.py` | Fully implemented (status/add_all/commit/current_branch). **Verified: constructed by `Updater.__init__` but never called** by either of `Updater`'s two methods; not called by `EvolutionBrain.evolve()` either. |
| `CodeGenerator` | `generator.py` | Fully implemented; calls `OllamaProvider` directly (bypasses `AIRouter`). **Verified reachable** — called by `EvolutionBrain.evolve()`. |
| `AutoFixer` | `autofix.py` | Fully implemented; re-prompts Ollama on review failure. **Verified unreachable** — `grep -rn AutoFixer app/` finds only its own class definition; nothing constructs it. |
| `PatchReviewer` | `reviewer.py` | Fully implemented; AST syntax check + one hardcoded heuristic (`"package = app.skills"` string check). **Verified reachable but its verdict is discarded** — `EvolutionBrain.evolve()` calls `review()` but branches only on `PatchValidator`'s result (see `DESIGN_PRINCIPLES.md` #11). |
| `PatchValidator` | `validator.py` | Fully implemented; AST syntax check + `importlib.util.find_spec` resolution check for every `app.*` import in the patch. **Verified reachable** — this is the check that actually gates `EvolutionBrain.evolve()`'s READY/BLOCKED verdict. |
| `Installer` | `installer.py` | Stub — returns a static "waiting for approval" string, no actual install logic. **Verified unreachable** from `EvolutionBrain.evolve()`. |
| `Analyzer` | `analyzer.py` | Fully implemented dataclass-returning file/line/sha256 scanner. **Verified: only called by `Updater.status()`** (which is itself real) — not part of `EvolutionBrain.evolve()`. |
| `Benchmark` | `benchmark.py` | Fully implemented — times a callable, catches exceptions as `success=False`. **Verified: constructed by `Updater.__init__`, never called by either `Updater` method or by `EvolutionBrain.evolve()`.** |
| `EvolutionBrain`, `EvolutionManager` | `brain.py`, `manager.py` | `EvolutionManager.run()` → `EvolutionBrain.evolve()` is **the one real, callable end-to-end pipeline in this package** — see `EVOLUTION_ENGINE.md` §Orchestration for its exact call graph (scanner → planner → interactive `input()` → generator → reviewer → validator). Hardcodes exactly 4 possible improvement targets via `EvolutionBrain.TASKS`. |
| `ContextBuilder` | `context_builder.py` | Fully implemented — writes `data/project_tree.txt`. **Verified reachable** — called by `CodeGenerator.generate_task`. |
| `EvolutionPlanner` | `planner.py` | Fully implemented; calls `OllamaProvider` directly (bypasses `AIRouter` — third such file, see `AI_SYSTEM.md` #2). **Verified reachable** — called first in `EvolutionBrain.evolve()`. |
| `RollbackManager` | `rollback.py` | Fully implemented — `create_backup`/`restore` via `shutil.copytree`. **Verified: constructed by `Updater.__init__`, never called by either `Updater` method or by `EvolutionBrain.evolve()`.** |
| `ProjectScanner` | `scanner.py` | Fully implemented — AST-walks `app/`, writes `data/evolution_report.json`. **Verified reachable** — called first (before the planner) in `EvolutionBrain.evolve()`. |
| `TestRunner` | `tester.py` | Fully implemented — subprocess-runs `python -m pytest <target>`. **Verified: constructed by `Updater.__init__`, never called by either `Updater` method or by `EvolutionBrain.evolve()`.** |
| `Updater` | `updater.py` | Constructs all 8 pipeline-stage objects in `__init__`. `status()` is real (calls `analyzer.analyze()` + `version.info()`); `upgrade_requested()` is a stub that ignores all 8 constructed dependencies and returns a canned success message. See `EVOLUTION_ENGINE.md` §Orchestration. |
| `VersionManager`, `Version` | `version.py` | Fully implemented — reads/writes `data/version.json`; defaults to `Version(0, 6, 0)` if the file doesn't exist yet. **This is an actively-executing third source of the "0.6.0" version drift** documented in `JARVIS_ARCHITECT.md`, not just a stale comment. Called only by `Updater.status()`. |
