# Design Principles & Architecture Review

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. This is the master weakness list — other docs
> (`MEMORY_SYSTEM.md`, `PLUGIN_SYSTEM.md`, `EVOLUTION_ENGINE.md`,
> `SECURITY_GUIDE.md`) each own the detailed fix for one or more numbered
> weaknesses below; keep them in sync when either side changes.

## Patterns Already Present (keep and extend these)

| Pattern | Where | Assessment |
|---|---|---|
| Dependency Injection / Service Locator | `ServiceRegistry` (`app/core/registry.py`), injected into skills via `Skill.setup(registry)` | Simple, works. A named-key registry is a service-locator, not pure DI — acceptable at this scale, but new code should still request only what it needs (`registry.get("memory")`), not the whole registry, to keep dependencies explicit. |
| Template Method | `Skill.execute()` calling the abstract `run()`, timing it, catching exceptions, normalizing the result | Well-executed. This is the pattern to replicate for `AIProvider` (see below) and for evolution pipeline stages. |
| Strategy | `SkillManager` mapping intent → `Skill` instance; `AIRouter` mapping provider name → provider instance | Correct shape. Currently undermined by `app/skills/generated/calculator.py` not implementing the `Skill` strategy interface at all (see `PLUGIN_SYSTEM.md`). |
| Pipeline / Chain | `CortexPipeline` (`input → normalize → detect intent → extract entities → select brain`); Evolution Engine's real orchestrated path (`scan → plan → generate → review + validate`, via `EvolutionBrain.evolve()` — see `EVOLUTION_ENGINE.md` §Orchestration; the wider stage catalog exists but most of it isn't wired into that path) | The clearest architectural asset in the codebase. Each stage is a small, focused class. This is the pattern new subsystems should follow — including finishing the wiring of the Evolution Engine's own remaining stages. |
| Publish/Subscribe | `EventBus` | Correct implementation, but see "Global singleton" weakness below. |
| Repository-ish persistence | `MemoryStorage` (JSON file per collection) | Adequate for this scale; the get/set/delete/clear interface is a reasonable minimal repository contract. |

## Weaknesses, and Why They Exist

### 1. Two competing routing implementations
`app/core/router.py::CommandRouter` and the `app/cortex/` intent pipeline
solve overlapping problems (turning free text into a routed action) with
different vocabularies (`CommandType` vs `Intent`) and different levels of
sophistication. **Why it exists**: the `.ps1` upgrade script history
(`upgrade_ai_planner_v1.ps1`, `upgrade_context_builder_v6.ps1`, etc.) shows
the codebase was built as a sequence of independently-scoped patches, several
of which introduced parallel subsystems for the same concern instead of
extending the existing one. There is no module boundary/interface that would
have forced a single owner for "text → action" translation.
**Fix direction**: `app/cortex` should become the single owner; `CommandRouter`
should be deleted once `Dispatcher` is wired into the kernel boot sequence.

### 2. Memory engine has three chained, independently-fatal bugs
`manager.py` imports `MemoryItem` from `.models`, but `models.py` only
defines `MemoryRecord` — this is an `ImportError` at **import time**,
before `MemoryManager` is ever constructed. If that's fixed,
`MemoryStorage.__init__(self, filename: str)` requires a filename but
`MemoryManager.__init__` calls `MemoryStorage()` with no argument — a
`TypeError` at construction time. If that's also fixed,
`MemoryManager.remember()` calls `self.storage.save_item(item)`, a method
`MemoryStorage` does not define — an `AttributeError` at call time.
`JarvisKernel.boot()` triggers the first of these unconditionally (any
import of `app.memory` fails), so the kernel as shipped cannot boot. **Why
it exists**: `storage.py` was evidently refactored to be collection-aware
(one JSON file per named collection, matching the five files under
`data/memory/`) after `manager.py` was written against an earlier,
differently-shaped version of both `models.py` and `storage.py` — three
separate refactors that never got reconciled against each other. **Fix
direction**: see `MEMORY_SYSTEM.md` for the full three-link chain and the
specific contract `MemoryManager` needs to satisfy at each link.

### 3. Generated skills are not loadable skills
`SkillGenerator` (`app/generator/skill_generator.py`) renders
`SKILL_TEMPLATE`, which produces a bare class with a `name` attribute and a
`run(self, **kwargs)` method — it does not subclass `Skill`, has no `intent`
attribute, and `run`'s signature doesn't match `Skill.run(self, request)`.
`SkillLoader` only registers classes that are `issubclass(obj, Skill)`, so
anything the generator produces is silently invisible to the runtime skill
system. **Why it exists**: the generator and the skill runtime were clearly
built at different times (the runtime uses ABC + dataclass results; the
generator predates or was never updated to match it) without a shared
contract test to catch the drift. **Fix direction**: see `PLUGIN_SYSTEM.md`.

### 4. Kernel, GUI, Cortex, and AI layer are four disconnected islands
`main.py` boots the kernel only; `app.py` builds a GUI window without a
registry; `Dispatcher` and `CortexPipeline` are never instantiated by
anything; nothing calls `AIManager`. **Why it exists**: each subsystem was
built and (partially) tested in isolation — reasonable for early-stage
development — but no integration layer was ever added to connect them.
**Fix direction**: tracked as the top roadmap item; do not paper over it by
having, e.g., a skill reach into `app.gui` directly.

### 5. Global singleton alongside a DI container
`app/core/event_bus.py` defines both the `EventBus` class *and* a
module-level `event_bus = EventBus()` instance, while `ServiceRegistry` also
registers an `EventBus` instance under `"event_bus"`. Nothing currently
guarantees these are the same instance if both are used. **Fix direction**:
delete the module-level singleton; everything must obtain the event bus via
the registry.

### 6. Duplicated/near-duplicated logging setup
`JarvisLogger` centralizes `logging.basicConfig`, but `app/evolution/sandbox.py`
calls `logging.getLogger(__name__)` directly, bypassing the centralized
formatter/handler configuration (and running the risk of misconfigured
logging if `Sandbox` is imported before `JarvisLogger.setup()` runs).
**Fix direction**: see `LOGGING_GUIDE.md`.

### 7. Missing interfaces/abstractions for the AI provider layer
`AIRouter` hardcodes a dict of five concrete provider classes; there is no
`Protocol`/`ABC` defining what a provider must implement, even though all
five happen to share a `generate(prompt: str) -> str` shape by convention.
**Why it matters**: nothing enforces the contract, so a sixth provider could
silently omit `generate` and only fail at call time. **Fix direction**:
introduce an `AIProvider` Protocol (see `AI_SYSTEM.md`) mirroring the `Skill`
ABC pattern that already works well elsewhere in the codebase.

### 8. Config is not environment-portable
`Config.APPLICATIONS` hardcodes a Windows path
(`C:\Program Files\Google\Chrome\Application\chrome.exe`) and bare `.exe`
names; `Config.ROOT = Path.cwd()` ties all derived paths to the current
working directory rather than the package's install location, meaning
`Config.DATA_DIR` etc. silently point somewhere else if JARVIS OS is launched
from a different directory. **Fix direction**: derive `ROOT` from
`Path(__file__).resolve().parents[2]` (as `app/evolution/sandbox.py` already
does correctly for `PROJECT_ROOT`), and move OS-specific app paths behind a
small platform-detection layer.

### 9. Security posture is inconsistent across subsystems
`app/skills/application/launcher.py` uses an explicit allow-list
(`Config.APPLICATIONS`) before calling `subprocess.Popen` — this is the
correct pattern. `app/evolution/sandbox.py::SecurityValidator` uses a
deny-list (`BLOCKED_IMPORTS`/`BLOCKED_CALLS`/`BLOCKED_ATTRIBUTES`) for
LLM-generated code, and its own docstring is honest about the limitation:
*"This is a guardrail, not a security boundary."* Deny-lists are inherently
incomplete (e.g. network access via a not-yet-blocked module, or filesystem
writes via any `Path` method other than the four listed). See
`SECURITY_GUIDE.md` for the full assessment — this is flagged as a design
weakness to monitor, not something to "fix" by expanding the deny-list
indefinitely.

### 10. No abstraction boundary between skills and generated skills
There is no `app/skills/generated/__init__.py` contract or registration hook
distinguishing "hand-written" from "AI-generated" skills, even though the
Evolution Engine is explicitly designed to write code into that directory.
Combined with weakness #3, this means the self-modifying half of the system
(Evolution Engine) and the skill-execution half of the system (SkillLoader)
do not actually agree on what a valid skill looks like.

### 11. Two independent, unreconciled patch checkers in the Evolution Engine
`reviewer.py` (`PatchReviewer`) and `validator.py` (`PatchValidator`) both
answer "is this generated patch safe?" with different, non-overlapping
checks and different report files, and neither is aware of the other.
`EvolutionBrain.evolve()` calls both but only branches on `PatchValidator`'s
verdict, silently discarding `PatchReviewer`'s. **Why it exists**: same root
cause as weakness #1 — two upgrade scripts each independently built "the
thing that checks the patch" without reconciling against what already
existed. **Fix direction**: see `EVOLUTION_ENGINE.md` §"Two Independent
Patch Checkers" — either merge the two into one contract, or have
`EvolutionBrain.evolve()` require both verdicts to agree before printing
"[READY]".

### 12. A documented skill that is actually an empty file
`app/skills/system/info.py` is 0 bytes — no class, no code, nothing. Every
other skill file (`browser/search.py`, `ai/chat.py`) correctly subclasses
`Skill` with a matching `intent` and `run(self, request)` signature, so this
isn't a systemic pattern-drift like weakness #3 — it looks like a file that
was scaffolded (created, named, referenced in the project tree) and never
actually written. **Fix direction**: either implement `SystemInfoSkill`
(`intent="system_info"` would match the naming convention of the two working
skills) or remove the empty file so `PROJECT_STRUCTURE.md`/`MODULE_GUIDE.md`
stop listing it as if it does something.

## Scalability & Performance Notes

- `MemoryStorage` rewrites the entire JSON file on every `set()` call — fine
  at current scale (a few KB), but will not scale past a few thousand memory
  entries without moving to an indexed/append-only format or a real embedded
  database (e.g. SQLite). (Note: `MemoryManager.remember()` currently calls
  a `save_item()` method that doesn't exist on `MemoryStorage` — see
  `MEMORY_SYSTEM.md` Link 3 — so this scalability note applies to `set()`
  once that call site is fixed to use a real method.)
- `SessionMemory` correctly bounds itself with `deque(maxlen=20)` — good
  practice, worth applying to `MemoryHistory.get_recent` at the storage layer
  too (currently loads the *entire* file and slices in Python).
- `Sandbox.run()` is synchronous and single-shot per call — acceptable for an
  interactive "review one patch" workflow, but will serialize badly if the
  Evolution Engine is ever asked to batch-evaluate multiple candidate patches.

## Target Layering (for new work)

```
Domain/Models     — dataclasses, enums, Protocols. No I/O, no framework imports.
                     (SkillResult, MemoryRecord, CortexRequest, a future AIProvider Protocol)
Application        — orchestration: Kernel, Dispatcher, CortexPipeline, Evolution stages.
                     Depends only on Domain + abstractions, injected via ServiceRegistry.
Infrastructure     — concrete I/O: MemoryStorage (JSON), AI providers (HTTP/SDK),
                     subprocess-based skills, customtkinter GUI, sounddevice/whisper voice.
                     Depends on Application-level abstractions; never the reverse.
```

Use this as the checklist when reviewing where a new class belongs.
