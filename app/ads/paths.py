from __future__ import annotations

import os
from pathlib import Path


def _resolve_base() -> Path:
    env = os.environ.get("JARVIS_RUNTIME_DIR")
    if env:
        return Path(env).resolve()
    return Path("runtime").resolve()


RUNTIME_DIR = _resolve_base()

# Subdirectory paths
GENERATED_DIR = RUNTIME_DIR / "generated"
INSTALLED_DIR = RUNTIME_DIR / "installed"
LOGS_DIR = RUNTIME_DIR / "logs"
CACHE_DIR = RUNTIME_DIR / "cache"
TEMP_DIR = RUNTIME_DIR / "temp"
WORKSPACE_DIR = RUNTIME_DIR / "workspace"
BACKUPS_DIR = RUNTIME_DIR / "backups"
SNAPSHOTS_DIR = RUNTIME_DIR / "snapshots"
METRICS_DIR = RUNTIME_DIR / "metrics"


def ensure_dirs() -> None:
    for d in (GENERATED_DIR, INSTALLED_DIR, LOGS_DIR, CACHE_DIR,
              TEMP_DIR, WORKSPACE_DIR, BACKUPS_DIR, SNAPSHOTS_DIR, METRICS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# Ensure runtime directories exist on import
ensure_dirs()
