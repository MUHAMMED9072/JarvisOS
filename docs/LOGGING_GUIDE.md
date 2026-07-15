# Logging Guide

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `DESIGN_PRINCIPLES.md` #6 (duplicated logging
> setup).

## The Standard: `JarvisLogger`

```python
from app.core.logger import JarvisLogger

JarvisLogger.info("message")
JarvisLogger.warning("message")
JarvisLogger.error("message")
JarvisLogger.debug("message")
```

`JarvisLogger` is a classmethod-only wrapper around `logging.basicConfig`:

- Lazily calls `setup()` on first use (`_initialized` guard — safe to call
  from any import order).
- Configures a `FileHandler` (`logs/jarvis.log`) and a `StreamHandler`
  (stdout/stderr) with a shared format:
  `"%(asctime)s | %(levelname)s | %(message)s"`.
- Level fixed at `INFO` in code (note: `Config.LOG_LEVEL = "INFO"` exists as
  a constant but `JarvisLogger.setup()` does not currently read it —
  hardcodes `logging.INFO` directly instead of `getattr(logging,
  Config.LOG_LEVEL)`. This is a small drift worth closing so `Config` is the
  actual source of truth it claims to be).

## Known Inconsistency

`app/evolution/sandbox.py` does not use `JarvisLogger`:

```python
LOGGER = logging.getLogger(__name__)
```

This bypasses `JarvisLogger`'s centralized formatter/handler setup. In
practice, because `logging.getLogger(__name__)` returns a logger that
propagates to the root logger, and `JarvisLogger.setup()` configures the
root logger via `basicConfig`, output *happens* to still reach
`logs/jarvis.log` and stdout **if `JarvisLogger.setup()` has already run
before `sandbox.py`'s logger emits anything** — but this is incidental, not
guaranteed. If `Sandbox` is ever used standalone (its own `if __name__ ==
"__main__":` block at the bottom of the file suggests it is sometimes run
directly) before any `JarvisLogger` call has occurred, `logging.basicConfig`
has never been invoked and the log format/destination falls back to
Python's default (stderr only, no file, default format).

## Rule Going Forward

- All new and edited code uses `JarvisLogger`, not `logging.getLogger(...)`
  directly.
- `app/evolution/sandbox.py`'s `LOGGER = logging.getLogger(__name__)` should
  be reconciled to call through `JarvisLogger` in a dedicated cleanup change
  (tracked in `ROADMAP.md`) — do this as an isolated, reviewable change
  since `sandbox.py` is otherwise stable and well-tested; don't bundle it
  into an unrelated feature change.
- Log messages should not duplicate information already visible from
  context (see `CODING_STANDARDS.md`'s "unnecessary comments" rule — the
  same principle applies to log messages: `JarvisLogger.info(f"{len(self
  .skill_manager.skills)} Skills Loaded")` is good, specific, and useful;
  banner lines like `self.logger.info("=" * 60)` in `kernel.py` are
  cosmetic and should not be treated as a pattern to replicate in new code).
- Never log secrets (API keys, `.env` contents) — see `SECURITY_GUIDE.md`.

## Gaps

- No log rotation configured (`FileHandler`, not `RotatingFileHandler` —
  `logs/jarvis.log` will grow unbounded).
- No structured logging (JSON) option — fine for a single-user desktop app
  today, worth reconsidering only if JARVIS OS ever needs machine-parseable
  logs (e.g. feeding logs back into the Evolution Engine's `analyzer.py`).
- `Config.LOG_LEVEL` is defined but not wired to `JarvisLogger.setup()` (see
  above) — closing this gap would let a user lower verbosity via config
  instead of editing `logger.py`.
