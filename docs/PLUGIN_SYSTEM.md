# Plugin System (Skills)

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `MODULE_GUIDE.md` (per-class status),
> `DESIGN_PRINCIPLES.md` #3/#10/#12 (generator incompatibility, missing
> abstraction boundary, empty `system/info.py`).

## Contract

Every skill **must**:

1. Subclass `app.skills.base.Skill`.
2. Set a non-empty class attribute `intent: str` (raises `ValueError` at
   registration time via `SkillManager.register` if missing).
3. Implement `run(self, request) -> SkillResult` (the abstract method).
   `request` is a `CortexRequest`-shaped object exposing at minimum
   `.entities` (dict) when used with `ApplicationLauncher`-style extraction.
4. Not override `execute()` — that's the template method that adds timing
   and exception safety; overriding it defeats the pattern.

```python
from app.skills.base import Skill
from app.skills.result import SkillResult

class MySkill(Skill):
    name = "My Skill"
    intent = "my_intent"
    version = "1.0.0"
    description = "What this does"

    def run(self, request) -> SkillResult:
        return SkillResult.ok(message="done")
```

## Discovery & Registration Flow

```
SkillLoader.load(manager, registry)
   → pkgutil.walk_packages(app.skills.__path__, "app.skills.")
   → for every submodule not named base/manager/loader/result:
       importlib.import_module(module_name)
       for every class in that module where issubclass(cls, Skill) and cls is not Skill:
           instance = cls()
           instance.setup(registry)     # injects memory, event_bus, skill_manager
           manager.register(instance)   # keyed by instance.intent
```

This is reflection-based auto-discovery — **dropping a new file under
`app/skills/` that defines a `Skill` subclass is enough to register it**, no
manual wiring required. This is a real strength of the current design and
should be preserved in any refactor.

## The Generator Incompatibility (must fix before relying on generated skills)

`app/generator/templates.py`:

```python
SKILL_TEMPLATE = """
class {class_name}:
    name = "{skill_name}"

    def run(self, **kwargs):
        return {body}
"""
```

This produces a class that:

- Does not subclass `Skill` → `SkillLoader`'s `issubclass(obj, Skill)` check
  silently skips it. It will never be registered, no error is raised.
- Has no `intent` attribute → even if it were registered, `SkillManager`
  would reject it.
- Defines `run(self, **kwargs)` instead of `run(self, request)` → incompatible
  call signature with `Skill.execute()`.

`app/skills/generated/calculator.py` is a concrete instance of this: a
working regex-based calculator as a **plain Python class**, invisible to the
skill runtime. It can be imported and used directly
(`CalculatorSkill().run("add 5 and 10")`) but not through the
intent-routing path any other skill uses.

### Required Fix (Phase 5 item — confirm scope with user before implementing)

Rewrite `SKILL_TEMPLATE` to:

```python
SKILL_TEMPLATE = '''
from app.skills.base import Skill
from app.skills.result import SkillResult


class {class_name}(Skill):
    name = "{skill_name}"
    intent = "{intent}"
    version = "1.0.0"
    description = "{description}"

    def run(self, request) -> SkillResult:
        return SkillResult.ok(message={body})
'''
```

`SkillGenerator.create()` would need a new required `intent` parameter (it
currently derives only a class name from `skill_name`, with no `intent`
field at all) and `SkillInstaller.install()` would need to actually call
`SkillManager.register(...)` after import — today it only imports the
module and returns it, performing no registration.

## `SkillResult` Contract

```python
@dataclass
class SkillResult:
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0     # overwritten by Skill.execute()
    skill: str = ""                # overwritten by Skill.execute() to self.name

    @classmethod
    def ok(cls, message="", data=None): ...
    @classmethod
    def fail(cls, message="", data=None): ...
```

`Skill.execute()` overwrites `result.skill` and `result.execution_time`
after `run()` returns, so a skill implementation should not bother setting
those fields itself.

## Fallback Behavior

`SkillManager.get(intent)` returns `FallbackSkill` (`intent = "unknown"`) for
any intent with no registered handler — this means `SkillManager.get()`
never raises and never returns `None`, which is a good invariant for callers
(`Dispatcher.dispatch` relies on this). Preserve this guarantee in any
refactor.

## Existing Skills (all verified against source)

| Skill | Intent | Notes |
|---|---|---|
| `ApplicationLauncher` | `open_application` | Correct allow-list pattern — see `SECURITY_GUIDE.md`. |
| `MemoryRecallSkill` | `memory_recall` | Depends on `MemoryManager.get_last_application()` — blocked by the `MEMORY_SYSTEM.md` three-link bug chain until fixed. |
| `FallbackSkill` | `unknown` | Default handler, always registered by `SkillManager.__init__`. |
| `BrowserSearch` (`browser/search.py`) | `search_web` | **Verified**: correctly subclasses `Skill`, matching `run(self, request)` signature. Returns a canned "Searching for: {query}" — no actual search backend wired up yet. |
| `ChatSkill` (`ai/chat.py`) | `chat` | **Verified**: correctly subclasses `Skill`, matching signature. Returns a canned "Reasoning Brain will be connected later." — not wired to `AIRouter`. |
| `system/info.py` | — | **Verified: file is 0 bytes.** Not a skill, not a stub with a `NotImplementedError` — completely empty. Do not list this as an existing skill in any other document; see `DESIGN_PRINCIPLES.md` #12. |

## When Adding a New Skill

1. Confirm the `intent` string doesn't already exist in `SkillManager` (no
   duplicate-detection exists today — the second `register()` call for the
   same intent silently overwrites the first, since `self.skills[intent] =
   skill` has no existence check, unlike `ServiceRegistry.register`, which
   does raise on duplicates. This asymmetry is worth reconciling).
2. Only request what you need via `self.memory`/`self.event_bus`/
   `self.skill_manager` (populated by `setup()`) — don't reach into
   `app.core.registry` directly from a skill.
3. Return `SkillResult.ok(...)`/`SkillResult.fail(...)`, never raise from
   `run()` for expected failure cases (unexpected exceptions are already
   caught by `execute()` and converted to a failed `SkillResult`, but that
   path loses the specific error type — prefer handling known failure modes
   explicitly).
