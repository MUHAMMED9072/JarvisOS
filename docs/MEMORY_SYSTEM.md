# Memory System

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `MODULE_GUIDE.md` §app.memory (per-class
> status), `TESTING_GUIDE.md` priority 1 (the regression test this bug
> chain needs), `DESIGN_PRINCIPLES.md` #2 (why this exists).

## Intended Architecture (per `app/memory/__init__.py`'s docstring)

```
storage · session · history · projects · preferences · knowledge · search · context
```

## What Actually Exists

| Submodule | Real code? |
|---|---|
| `storage.py` | Yes |
| `session.py` | Yes |
| `history.py` | Yes |
| `models.py` | Yes (not listed in the docstring, but implemented) |
| `manager.py` | Yes (not listed in the docstring, but implemented — the facade) |
| `projects.py` | No — stub |
| `preferences.py` | No — stub |
| `knowledge.py` | No — stub |
| `search.py` | No — stub |
| `context.py` | No — stub |

## Critical Bug: `app.memory` cannot even be imported, let alone constructed

This is a chain of **three** separate, independently-fatal bugs, verified in
this order by actually attempting the import (`python -c "import
app.memory.manager"`) rather than reasoning about it statically. Each bug
hides the next one — fixing #1 alone does not make `MemoryManager` work; you
must fix all three in the same change (also true of `ROADMAP.md` P0-1a/b/c,
which now has three sub-items to match, replacing the previous two-item
framing).

### Link 1 (actually fires first): `ImportError` on `MemoryItem`

```python
# manager.py, line 4
from .models import MemoryItem
```

`app/memory/models.py` defines only `MemoryRecord` — there is no `MemoryItem`
class anywhere in the module. This makes the `from .models import
MemoryItem` line fail at **import time**, before any code in `manager.py`
runs, before `JarvisKernel.__init__` gets anywhere near calling
`MemoryManager()`. Confirmed directly:

```
Traceback (most recent call last):
  ...
  File "app/memory/manager.py", line 4, in <module>
    from .models import MemoryItem
ImportError: cannot import name 'MemoryItem' from 'app.memory.models'
```

Since `app/memory/__init__.py` does `from .manager import MemoryManager`,
this `ImportError` propagates to **any** import of `app.memory` at all — not
just to code paths that construct a `MemoryManager`.

### Link 2 (would fire next, once #1 is fixed): `TypeError` on `MemoryStorage()`

`MemoryStorage.__init__` requires a `filename`:

```python
# storage.py
def __init__(self, filename: str):
    self.path = Path("data") / "memory" / filename
    ...
```

`MemoryManager.__init__` calls it with **no argument**:

```python
# manager.py
def __init__(self):
    self.storage = MemoryStorage()   # TypeError: missing 'filename'
```

This is real and matches the original analysis, but it is the **second**
failure in the chain, not the first — it is currently unreachable because
Link 1 fires before the interpreter ever gets to evaluate this line at
runtime.

### Link 3 (would fire after #1 and #2 are both fixed): `AttributeError` on `save_item`

`MemoryManager.remember()` calls:

```python
self.storage.save_item(item)
```

`MemoryStorage` (`storage.py`) defines only `load`, `save`, `get`, `set`,
`delete`, `clear` — there is no `save_item` method. Even with `MemoryItem`
defined and `MemoryStorage()` given a filename, the first call to
`remember()` would raise `AttributeError: 'MemoryStorage' object has no
attribute 'save_item'`.

### Net effect

`JarvisKernel.boot()` does `self.memory = MemoryManager()` unconditionally in
`JarvisKernel.__init__`. Today, that line is never reached — the process
fails at `import app.memory` (Link 1), which happens as soon as
`app/core/kernel.py` (or anything importing it) is imported. This is the
single highest-priority fix in `ROADMAP.md` (see `ROADMAP.md` P0-1a/b/c) —
and all three links must be closed together, in the same change, or the
"fix" will just move the crash one line deeper.

See `JARVIS_ARCHITECT.md` §4 for how this fits into the overall integration
picture, and `TESTING_GUIDE.md` priority 1 for the regression test that
should be written first (and would have caught all three links, not just
the first one, if it asserted on a successful `remember()` call rather than
stopping at construction).

## Secondary Bug: `MemoryHistory` assumes a list, `MemoryStorage` returns a dict

`MemoryStorage.load()` returns `dict` (it initializes with `self.save({})`
and `json.load` reads whatever's on disk — a JSON object).

`MemoryHistory` treats `storage.load()` as a **list**:

```python
def get_recent(self, limit: int = 10):
    return self.storage.load()[-limit:]     # slicing a dict raises TypeError

def search(self, query: str):
    return [m for m in self.storage.load() if query in m.get("content", "")]
    # iterating a dict yields its *keys* (strings), and str has no .get()
```

This means even a correctly-constructed `MemoryStorage` would not satisfy
`MemoryHistory`'s expectations. The two classes were written against
different assumed data shapes.

## Root Cause

Judging by `data/memory/*.json` (five separate files: `history.json`,
`knowledge.json`, `preferences.json`, `projects.json`, `session.json`),
`MemoryStorage` was refactored at some point to be **one JSON-object-per-named-collection**
(matching the five stub submodules that were presumably meant to each own one
file). `MemoryManager`/`MemoryHistory`, however, were written against an
earlier design where `MemoryStorage` held a **single flat list of memory
items** (consistent with `tests/_storage.py`'s single `db.set("user", ...)`
call and with `MemoryManager.remember()`'s intent — append one item per
turn). The refactor was applied to `storage.py` without updating its
callers.

## What `MemoryManager` Actually Needs From Storage

Based on how `manager.py` and `history.py` use it, the storage layer needs
two distinct behaviors that got collapsed into one class:

1. **An append-only list of timestamped items** (role/content/metadata) —
   what `remember()`, `get_recent()`, `search()`, `last_user_message()`, and
   `last_assistant_message()` all assume.
2. **A flat key/value store** — what `get()`/`set()`/`delete()` on
   `MemoryStorage` actually implement, and what `tests/_storage.py` exercises.

These are two different repository shapes. Recommended fix direction (do not
implement without confirming scope with the user first, per
`JARVIS_ARCHITECT.md` §7):

- Keep `MemoryStorage(filename)` as the generic key/value JSON repository —
  it's correctly implemented for that purpose and matches the five
  `data/memory/*.json` collection files.
- Give `MemoryManager` its own list-backed store — e.g.
  `MemoryStorage("history.json")` where the value at a single well-known key
  (`"items"`) holds the list, or a small dedicated `MemoryItemStore` class —
  and update `MemoryHistory` to read/write through that shape consistently.
- Add a `MemoryItem.create(role, content, metadata)` classmethod (referenced
  by `manager.py` but not present in `models.py` today — only `MemoryRecord`
  exists) or reconcile `manager.py` to construct `MemoryRecord` instead.

## Working Parts (safe to build on as-is)

- `SessionMemory` — bounded in-memory deque, correct and self-contained.
- `MemoryStorage.get/set/delete/clear` — correct generic JSON key/value CRUD,
  verified by `tests/_storage.py`.
- `MemoryRecord` — correct dataclass shape for a single key/value entry with
  timestamps.

## Test Coverage Today

`tests/_storage.py` is a manual script (no `assert`, no pytest, prints to
stdout) that only exercises `MemoryStorage.set`/`.get` in isolation. It does
not catch any of the bugs documented above (the three-link `MemoryManager`
chain or the `MemoryHistory` list/dict mismatch) because it never
constructs `MemoryManager` or `MemoryHistory` — it only calls the two
`MemoryStorage` methods that already work correctly. See `TESTING_GUIDE.md`
for the pytest suite this needs.
