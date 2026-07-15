# Sandbox Engine

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `EVOLUTION_ENGINE.md` (this sandbox is
> currently unreachable from the one real orchestration path — see its
> §Orchestration), `SECURITY_GUIDE.md` (why this is a guardrail, not a
> security boundary).

`app/evolution/sandbox.py` (317 lines) executes LLM-generated patches before
they can be reviewed by a human or committed. It is the most security-critical
file in the codebase and the best-engineered one. This document exists so
that future work does not weaken it by accident.

## Components

| Class | Responsibility |
|---|---|
| `WorkspaceManager` | Creates a disposable `tempfile.mkdtemp` directory per run; guarantees removal via `shutil.rmtree`, tolerating Windows' delayed-handle-release behavior with a logged warning rather than a crash. |
| `SecurityValidator` | Parses the candidate source with `ast`, resolves import aliases (so `from os import system as run` cannot evade detection), and flags blocked imports, blocked calls, and blocked attribute accesses. |
| `ProcessRunner` | Launches the script as `python -I <script>` (isolated mode — ignores user site-packages and `PYTHON*` env vars) in its own process group, polls for completion with a wall-clock timeout, tracks peak RSS and CPU time via `psutil` if installed, and force-kills the whole process tree (not just the parent) on timeout. |
| `SandboxReporter` | Writes both a human-readable `.txt` and a machine-readable `.json` report to `data/`, using atomic write-then-rename so a reader never sees a partial file. |
| `Sandbox` | Orchestrates the above: validate → (if clean) execute → report → cleanup, always, via `try/finally`. |

## The Deny-List (`SecurityValidator`)

```python
BLOCKED_IMPORTS = {"ctypes", "multiprocessing", "requests", "socket",
                    "subprocess", "telnetlib", "urllib", "http", "ftplib",
                    "ssl", "winreg"}
BLOCKED_CALLS = {"breakpoint", "compile", "eval", "exec", "exit", "globals",
                  "input", "locals", "open", "__import__", "getattr"}
BLOCKED_ATTRIBUTES = {"os.system", "os.popen", "os.remove", "os.rename",
                       "os.replace", "os.rmdir", "os.unlink", "os.walk",
                       "os.chmod", "os.chown", "os.environ",
                       "pathlib.Path.unlink", "pathlib.Path.rmdir",
                       "pathlib.Path.rename", "pathlib.Path.replace",
                       "shutil.rmtree", "shutil.move", "shutil.copy",
                       "sys.exit"}
```

## What This Is — and Explicitly Is Not

The module's own docstring states it plainly:

> *"This is a guardrail, not a security boundary. Untrusted code must still
> be run in an operating-system/container sandbox for strong isolation."*

Take this at face value. Concretely, the deny-list approach means:

- **It blocks known-bad patterns, not unknown ones.** A deny-list is
  inherently incomplete — e.g. `pathlib.Path.write_text` (not blocked) can
  still create/overwrite arbitrary files within the workspace's *and any
  other accessible* directory; `os.getenv`/`os.environ.get` are not blocked
  the way `os.environ` (attribute access) is, so environment secrets could
  still leak through print/return values.
- **`python -I` limits import surface but does not sandbox the filesystem or
  network.** Isolated mode stops the script from importing from the user's
  site-packages or picking up `PYTHONPATH`, but it does not chroot, does not
  apply seccomp/AppArmor, and does not restrict which paths on disk the
  process can read or write to (only the *listed* destructive calls are
  blocked, not filesystem access generally).
- **Resource limiting is monitor-and-kill, not OS-enforced.** CPU/RAM are
  polled and the process is killed if it exceeds the timeout — there is no
  `ulimit`/cgroup enforcing a hard ceiling, so a fork-bomb-style or
  extremely fast memory-spike script could do damage in the window between
  polls (`poll_interval=0.05`s by default — small, but non-zero).
- **No network sandboxing at all.** Blocking `socket`/`requests`/`urllib`/
  `http`/`ftplib` at the import level is a real deterrent but not a
  guarantee — any blocked-import bypass (e.g. a currently-unblocked stdlib
  module that can still reach the network, or a C-extension dependency)
  would not be caught.

## Recommendation (do not implement without user sign-off — see `SECURITY_GUIDE.md`)

Treat the current `SecurityValidator` as a fast, cheap first filter — it
correctly rejects the "obviously trying to do something destructive" case —
but do not expand its scope indefinitely as a substitute for real isolation.
The honest path forward, in priority order:

1. Run the subprocess inside an OS-level sandbox (Windows: a restricted job
   object / AppContainer; cross-platform: a container or a `firejail`-style
   wrapper on Linux) rather than a bare `subprocess.Popen`.
2. Deny network access at the OS/firewall level for the sandbox process,
   not just at the Python-import level.
3. Mount the workspace as the *only* writable path available to the process.
4. Keep the current AST deny-list as a pre-filter (it's cheap and catches
   the obvious cases before you even pay for process startup) — don't
   remove it, just don't treat it as sufficient on its own.

## Failure Modes Already Handled Well

- Timeout → whole process tree killed (`psutil` children-then-parent, with a
  `taskkill /T /F` fallback on Windows and `os.killpg` on POSIX).
- Sandbox setup failure (`OSError`/`SubprocessError`) → reported and cleaned
  up, not left as an orphaned temp directory or a silent crash.
- `psutil` not installed → degrades gracefully (metrics stay at 0, process
  killing falls back to OS-native commands) rather than raising `ImportError`
  at call time.

## Do Not

- Do not add new "convenience" blocked-call exceptions without discussing
  the security implication first — every entry removed from the deny-list
  widens what generated code can do to the host machine.
- Do not reuse a `Sandbox`/`WorkspaceManager` instance across concurrent
  runs without checking the `threading.RLock` usage still guarantees
  workspace isolation — it currently does, but this is easy to break by
  refactoring `run()` to be async without re-verifying the locking strategy.
