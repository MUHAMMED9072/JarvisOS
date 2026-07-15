# Security Guide

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `SANDBOX_ENGINE.md` (execution isolation for
> Evolution Engine patches), `EVOLUTION_ENGINE.md` (the self-modification
> pipeline this guide constrains).

## Secrets Management

- API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
  `DEEPSEEK_API_KEY`) and `OLLAMA_HOST` live in `.env`, loaded via
  `python-dotenv`'s `load_dotenv()` at the top of each provider module.
- `.env` **is correctly gitignored** (`.gitignore` includes `.env`) — this
  is working as intended and must not change.
- Each provider raises a `RuntimeError` naming the missing variable if its
  key is absent, rather than silently proceeding — good, keep this pattern
  for any new provider.
- **Do not** log full prompt/response payloads that might contain API keys
  or secrets accidentally echoed by a model; current `print()` statements
  in `generator.py`/`autofix.py` only log status strings, not payload
  content — preserve that boundary if converting these to `JarvisLogger`
  calls.

## Subprocess Execution — Two Different Postures

### 1. `ApplicationLauncher` (`app/skills/application/launcher.py`) — allow-list, correct

```python
applications = Config.APPLICATIONS   # fixed dict of known apps
if app not in applications:
    return SkillResult.fail(f"{app} is not supported.")
subprocess.Popen(applications[app])
```

This is the right pattern: user input is matched against a closed,
developer-controlled set of executables, never passed to `subprocess`
directly. Any new "launch X" style skill must follow this shape — resist
any request to make this "more flexible" by accepting arbitrary paths from
user/voice input, since that reintroduces arbitrary command execution.

### 2. Evolution Engine Sandbox (`app/evolution/sandbox.py`) — deny-list, honestly labeled as partial

Full breakdown in `SANDBOX_ENGINE.md`. Summary for this doc: it's a static
AST deny-list plus a resource/time-limited subprocess, and the code's own
docstring calls it a guardrail rather than a security boundary. Do not
present this sandbox to a user as fully isolating untrusted code — it
isn't, and the module's own author already documented that honestly.

## Windows-Specific Risk Surface

- `Config.APPLICATIONS` hardcodes a full path to `chrome.exe` under
  `C:\Program Files\...` — if this path doesn't exist on a given machine,
  `subprocess.Popen` will raise, which is a correctness issue more than a
  security one, but note it's an unvalidated hardcoded path (see
  `DESIGN_PRINCIPLES.md` #8 for the portability angle).
- `Sandbox`'s `ProcessRunner` uses `taskkill /PID ... /T /F` as a Windows
  fallback for killing a process tree — this shells out to a system binary
  with a PID it controls (not user input), which is safe as constructed;
  do not change this to accept an externally-supplied PID or add shell=True
  anywhere in this file.

## Git Operations

`GitManager` runs `git` with a fixed argument list built from method
parameters (`status`, `add_all`, `commit(message)`, `current_branch`) — no
shell interpolation, arguments passed as a list to `subprocess.run`, so
this is not shell-injectable via `message`. It also does not currently
validate `message` isn't empty, and there's no branch-protection or "are you
on the right branch" check before `commit` — worth adding before the
Evolution Engine is trusted to auto-commit unattended (`installer.py`
being a stub suggests this gate doesn't exist yet, which is appropriate for
the current maturity level — don't build auto-commit-on-approval without
discussing the approval mechanism with the user first).

## Data at Rest

- `data/memory/*.json` and other `data/*.json`/`.txt` report files are
  plaintext, unencrypted, world-readable-by-the-OS-user files. This is
  standard for a local single-user desktop assistant and not flagged as a
  problem at this stage, but if JARVIS OS is ever extended to store
  sensitive user data (credentials, personal documents) that assumption
  needs to be revisited explicitly, not silently inherited.

## Recommendations Summary (do not implement unprompted — flag to user first)

1. Move sandboxed execution from bare `subprocess.Popen` to a real OS-level
   isolation mechanism (see `SANDBOX_ENGINE.md` §Recommendation).
2. Add a genuine human-approval gate before `Installer`/`GitManager.commit`
   can apply an Evolution Engine patch to the live tree — decide and
   document what "approval" means (CLI prompt, GUI button, config flag)
   before implementing `Installer.install()` for real.
3. Normalize `Config.ROOT` to be package-relative (`Path(__file__).resolve()`
   based, like `sandbox.py`'s `PROJECT_ROOT` already does) rather than
   CWD-relative, so path-dependent security assumptions (e.g. "the sandbox
   workspace is always under a controlled temp root") don't silently break
   if JARVIS OS is launched from an unexpected working directory.
4. Add a `.gitattributes` normalizing line endings. **Verified (2026):**
   `git log --all --full-history -- .env` returns zero commits, and
   `git ls-files | grep .env` returns nothing — `.env` has never been
   committed and is not currently tracked. This check is now closed; no
   history-scrubbing action is required. Re-run this check as a matter of
   routine before any future public release, since it is cheap and the
   consequence of a silent regression (an `.env` accidentally added to a
   commit) is severe.
