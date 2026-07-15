# Project Structure

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index and `MODULE_GUIDE.md` for per-class status detail behind
> each file listed below.

Excludes `.venv/`, `.git/`, `__pycache__/` (present in the repo but not part
of the source of truth).

```
JarvisOS/
├── main.py                     Entry point. Boots JarvisKernel only (does not launch GUI).
├── requirements.txt            Dependency list (incomplete — see ROADMAP.md).
├── README.md                   Empty (0 bytes).
├── .env                        Provider API keys (gitignored — correct).
├── .gitignore                  Standard Python/venv/env/log excludes.
│
├── app/
│   ├── core/                   Kernel, DI registry, event bus, config, logging.
│   │   ├── app.py              JarvisApp — GUI entry point. NOT called by main.py.
│   │   ├── config.py           Config — static class of paths/constants. Windows-only paths.
│   │   ├── event_bus.py        EventBus — pub/sub. Also exports a module-level singleton.
│   │   ├── kernel.py           JarvisKernel — boot sequence, service registration.
│   │   ├── logger.py           JarvisLogger — classmethod wrapper over stdlib logging.
│   │   ├── registry.py         ServiceRegistry — name→instance DI container.
│   │   ├── router.py           CommandRouter — prefix-based text routing (overlaps app/cortex).
│   │   └── startup.py          Empty.
│   │
│   ├── cortex/                 NLU pipeline. Not wired into the kernel.
│   │   ├── pipeline.py         CortexPipeline — orchestrates the 5 steps below.
│   │   ├── input_manager.py    Wraps raw text into a CortexRequest.
│   │   ├── normalizer.py       Wake-word stripping, punctuation removal, synonym mapping.
│   │   ├── intent_detector.py  Intent enum + keyword/phrase-based detection.
│   │   ├── entity_extractor.py Extracts entities per intent (very simple slot filling).
│   │   ├── brain_selector.py   Maps Intent → BrainType (fast/smart/deep).
│   │   ├── dispatcher.py       Dispatcher — routes a CortexRequest to a Skill. Unused by kernel.
│   │   ├── models.py           CortexRequest / CortexResponse / BrainType dataclasses.
│   │   ├── context.py          Stub (near-empty).
│   │   ├── handlers/           ai_handler.py, automation_handler.py, developer_handler.py,
│   │   │                       memory_handler.py — all empty files.
│   │   └── brains/             deep_brain.py, fast_brain.py, smart_brain.py — all empty files.
│   │
│   ├── ai/                     Multi-provider AI abstraction.
│   │   ├── manager.py          AIManager — thin facade over AIRouter.
│   │   ├── router.py           AIRouter — provider name → provider instance map.
│   │   └── providers/          ollama.py (working), openai.py, claude.py, gemini.py,
│   │                           deepseek.py (all raise NotImplementedError).
│   │
│   ├── memory/                 Persistence engine. Contains a runtime-breaking bug — see MEMORY_SYSTEM.md.
│   │   ├── manager.py          MemoryManager — public facade.
│   │   ├── storage.py          MemoryStorage — JSON file read/write, keyed by filename.
│   │   ├── session.py          SessionMemory — in-memory ring buffer (deque) of recent turns.
│   │   ├── history.py          MemoryHistory — search/recent/last-message queries over storage.
│   │   ├── models.py           MemoryRecord dataclass (key/value/created/updated).
│   │   ├── context.py          Stub (malformed docstring, no code).
│   │   ├── knowledge.py        Stub.
│   │   ├── preferences.py      Stub.
│   │   ├── projects.py         Stub.
│   │   └── search.py           Stub.
│   │
│   ├── evolution/               Self-modifying code pipeline (most mature module
│   │   │                        at the per-file level; only partially wired
│   │   │                        together — see EVOLUTION_ENGINE.md §Orchestration).
│   │   ├── scanner.py           ProjectScanner — scans app/ for improvement candidates. Reachable.
│   │   ├── analyzer.py          Analyzer — file/line/hash scan. NOT reachable from the real entry point.
│   │   ├── planner.py           EvolutionPlanner — produces a change plan via Ollama. Reachable.
│   │   ├── context_builder.py   ContextBuilder — builds a project-tree prompt-context artifact. Reachable (via generator.py).
│   │   ├── generator.py         CodeGenerator — calls OllamaProvider to write a patch file. Reachable.
│   │   ├── reviewer.py          PatchReviewer — AST syntax check + shallow static checks. Reachable, but its verdict is discarded (see DESIGN_PRINCIPLES.md #11).
│   │   ├── validator.py         PatchValidator — AST syntax + app.* import resolution check. Reachable — this is the verdict that actually gates READY/BLOCKED.
│   │   ├── autofix.py           AutoFixer — re-prompts the LLM to repair review failures. NOT reachable — never constructed anywhere in the package.
│   │   ├── sandbox.py           Sandbox — isolated, resource-limited execution (see SANDBOX_ENGINE.md). NOT reachable from the real entry point.
│   │   ├── installer.py         Stub — "Waiting for user approval." NOT reachable.
│   │   ├── git_manager.py       GitManager — status/add/commit/branch via subprocess. NOT reachable (constructed by Updater, never called).
│   │   ├── rollback.py          RollbackManager — create_backup/restore via shutil.copytree. NOT reachable (constructed by Updater, never called).
│   │   ├── version.py           VersionManager — version bump/tracking; writes data/version.json (source of a live version-drift issue — see JARVIS_ARCHITECT.md §5). Called only by Updater.status().
│   │   ├── tester.py            TestRunner — subprocess-runs pytest. NOT reachable (constructed by Updater, never called).
│   │   ├── benchmark.py         Benchmark — times a callable. NOT reachable (constructed by Updater, never called).
│   │   ├── updater.py           Updater — status() is real (analyzer + version); upgrade_requested() is a stub that does NOT apply any patch despite constructing all 8 pipeline objects.
│   │   ├── brain.py             EvolutionBrain — the actual orchestrator. evolve() is the one real end-to-end pipeline (scanner→planner→generator→reviewer→validator).
│   │   └── manager.py           EvolutionManager — thin entry point: run() calls EvolutionBrain().evolve(). Runnable via `python -m app.evolution.manager`.
│   │
│   ├── skills/                  Plugin/command system.
│   │   ├── base.py               Skill(ABC) — template-method execute()/run() contract.
│   │   ├── manager.py             SkillManager — intent → Skill registry + fallback.
│   │   ├── loader.py              SkillLoader — pkgutil-based auto-discovery + DI injection.
│   │   ├── result.py              SkillResult dataclass (success/message/data/execution_time).
│   │   ├── application/launcher.py  ApplicationLauncher — whitelisted subprocess app launch.
│   │   ├── browser/search.py        Web search skill.
│   │   ├── ai/chat.py                AI chat skill.
│   │   ├── memory_recall/skill.py    MemoryRecallSkill — reads MemoryManager.
│   │   ├── system/info.py            EMPTY FILE (0 bytes) — not an implemented skill. See `MODULE_GUIDE.md`/`DESIGN_PRINCIPLES.md` #12.
│   │   ├── unknown/fallback.py       FallbackSkill — default "I don't know how" response.
│   │   └── generated/calculator.py   Output of SkillGenerator. Does NOT subclass Skill
│   │                                 (see PLUGIN_SYSTEM.md — incompatible with SkillLoader).
│   │
│   ├── generator/                Skill scaffolding tool (used by the Evolution Engine).
│   │   ├── skill_generator.py    SkillGenerator — renders SKILL_TEMPLATE to a new .py file.
│   │   ├── templates.py          SKILL_TEMPLATE string — produces plain classes, not Skill subclasses.
│   │   └── installer.py          SkillInstaller — importlib-based module import.
│   │
│   ├── voice/                    Voice I/O. Mostly stubs.
│   │   ├── manager.py             VoiceManager — enabled/disabled flag only.
│   │   ├── listener.py            VoiceListener — sounddevice-based fixed-length recording.
│   │   ├── providers/whisper_provider.py  faster-whisper transcription wrapper.
│   │   ├── recognizer.py, speaker.py, vad.py, wakeword.py, commands.py, config.py — all empty.
│   │
│   ├── gui/                      customtkinter desktop UI. Mostly stubs.
│   │   ├── window.py               JarvisWindow — main window (224 lines, implemented).
│   │   ├── theme.py                Design tokens: COLORS, WINDOW_WIDTH/HEIGHT, SIDEBAR_WIDTH.
│   │   ├── components/sidebar.py   Sidebar — nav buttons (Dashboard/AI Chat/Voice/.../Settings).
│   │   ├── components/status_card.py, statusbar.py, topbar.py — all empty.
│   │   └── pages/ai_chat.py, dashboard.py, settings.py — all empty.
│   │
│   ├── models/navigation.py      Shared navigation-related model(s).
│   ├── plugins/__init__.py       Empty — no third-party plugin system exists yet despite the folder.
│   ├── utils/system.py           OS-level helper utilities.
│   └── assets/                   Static assets (icons etc.).
│
├── data/                          Runtime artifacts (mostly generated, not hand-authored).
│   ├── memory/*.json              MemoryStorage-backed files (history, knowledge, preferences, projects, session).
│   ├── evolution_plan.json, evolution_report.json, sandbox_report.{json,txt},
│   │   review_report.txt, validation_report.txt, generated_patch.py,
│   │   improvement_plan.md, project_tree.txt   — Evolution Engine outputs.
│   ├── ai_prompt.txt              Prompt fragment used by the Evolution Engine.
│   └── version.json               Structured version metadata.
│
├── logs/jarvis.log                 JarvisLogger output.
├── tests/_storage.py                Manual smoke script, not a pytest suite (no assertions).
└── upgrade_*.ps1 (22 files)         PowerShell scripts that appear to have been used to apply
                                     prior incremental upgrades to this codebase outside of any
                                     tracked build/migration system. Explains inconsistent code
                                     quality across modules (see DESIGN_PRINCIPLES.md §Weaknesses).
```

## Naming Convention Observed

- Packages: lowercase, singular where the concept is singular (`kernel`,
  `router`), otherwise domain-plural (`skills`, `providers`).
- Classes: `PascalCase`, usually suffixed with role (`...Manager`, `...Loader`,
  `...Provider`, `...Skill`, `...Result`).
- No `interfaces/` or `contracts/` subpackage exists anywhere — abstractions
  (where they exist, e.g. `Skill(ABC)`) live next to their implementations.
  See `DESIGN_PRINCIPLES.md` for the recommended fix.
