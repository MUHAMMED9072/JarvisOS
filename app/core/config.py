from __future__ import annotations

from pathlib import Path

from app.ai.config import AIConfig
from app.voice.config import VoiceConfig


class Config:

    # ======================================================
    # JARVIS
    # ======================================================

    APP_NAME = "JARVIS OS"
    VERSION = "0.4.0-alpha"

    # ======================================================
    # PATHS
    # ======================================================

    ROOT = Path(__file__).resolve().parents[2]

    APP_DIR = ROOT / "app"

    DATA_DIR = ROOT / "data"

    LOG_DIR = ROOT / "logs"

    PLUGIN_DIR = APP_DIR / "plugins"

    MEMORY_DIR = ROOT / "memory"

    CACHE_DIR = ROOT / "cache"

    FILE_DIR = DATA_DIR / "files"

    # ======================================================
    # FILE TRANSFER
    # ======================================================

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    CHUNK_SIZE = 64 * 1024  # 64 KB

    # ======================================================
    # AI
    # ======================================================

    DEFAULT_BRAIN = "fast"

    REASONING_BRAIN = "reasoning"

    CODING_BRAIN = "coding"

    # Single source of truth for AI subsystem configuration.
    # Every AI component reads its settings from this object.
    AI = AIConfig()

    # ======================================================
    # VOICE
    # ======================================================

    # Backward-compatible voice constants. The single source of truth
    # for voice configuration is ``VOICE`` below — these two globals
    # are kept so legacy code (e.g. GUI strings) continues to work.
    WAKE_WORD = "jarvis"

    DEFAULT_LANGUAGE = "en"

    # Single source of truth for the voice subsystem. ``enabled``
    # defaults to ``False`` so headless / test runs are unaffected.
    VOICE = VoiceConfig()

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
