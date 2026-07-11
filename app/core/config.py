from __future__ import annotations

from pathlib import Path


class Config:

    # ======================================================
    # JARVIS
    # ======================================================

    APP_NAME = "JARVIS OS"
    VERSION = "0.4.0-alpha"

    # ======================================================
    # PATHS
    # ======================================================

    ROOT = Path.cwd()

    APP_DIR = ROOT / "app"

    DATA_DIR = ROOT / "data"

    LOG_DIR = ROOT / "logs"

    PLUGIN_DIR = APP_DIR / "skills"

    MEMORY_DIR = ROOT / "memory"

    CACHE_DIR = ROOT / "cache"

    # ======================================================
    # AI
    # ======================================================

    DEFAULT_BRAIN = "fast"

    REASONING_BRAIN = "reasoning"

    CODING_BRAIN = "coding"

    # ======================================================
    # VOICE
    # ======================================================

    WAKE_WORD = "jarvis"

    DEFAULT_LANGUAGE = "en"

    # ======================================================
    # LOGGING
    # ======================================================

    LOG_LEVEL = "INFO"

    LOG_FILE = LOG_DIR / "jarvis.log"

    # ======================================================
    # APPLICATIONS
    # ======================================================

    APPLICATIONS = {
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "explorer": "explorer.exe",
    }