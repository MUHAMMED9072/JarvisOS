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
    # WEBSOCKET AUTHENTICATION
    # ======================================================

    WS_AUTH_ENABLED = True
    WS_ANONYMOUS_ENABLED = True

    WS_AUTH_TIMEOUT = 30.0
    WS_SESSION_EXPIRY = 3600.0
    WS_TOKEN_EXPIRY = 86400.0

    WS_MAX_MESSAGES_PER_MINUTE = 120

    WS_AUTH_API_KEYS: dict[str, list[str]] = {
        "admin-key": ["admin"],
        "user-key": ["user"],
    }

    WS_AUTH_BEARER_SECRET = "change-me-in-production"

    WS_DEFAULT_ANONYMOUS_ROLES: list[str] = ["user"]
    WS_DEFAULT_ANONYMOUS_PERMISSIONS: list[str] = [
        "admin.ping", "admin.status", "admin.info",
        "command.*", "ai.*", "filesystem.*",
    ]

    # ======================================================
    # WEBSOCKET RELIABILITY & RESILIENCE (P12-09)
    # ======================================================

    WS_HEARTBEAT_ENABLED = True
    WS_ACTIVE_HEARTBEAT_ENABLED = True
    WS_HEARTBEAT_INTERVAL = 30.0
    WS_HEARTBEAT_TIMEOUT = 10.0

    WS_ACK_ENABLED = True
    WS_ACK_TIMEOUT = 30.0
    WS_MAX_RETRIES = 3
    WS_RETRY_INTERVAL = 5.0
    WS_RELIABLE_SEND_ENABLED = True

    WS_OFFLINE_QUEUE_ENABLED = True
    WS_OFFLINE_QUEUE_MAXSIZE = 100
    WS_OFFLINE_QUEUE_OVERFLOW = "drop_oldest"

    WS_RECONNECT_ENABLED = True
    WS_RECONNECT_TOKEN_EXPIRY = 300.0

    WS_STATS_ENABLED = True
    WS_MAX_EVENT_QUEUE_SIZE = 100

    WS_COMPRESSION_ENABLED = False
    WS_COMPRESSION_MIN_SIZE = 4096

    # ======================================================
    # WEBSOCKET PRODUCTION FEATURES & OBSERVABILITY (P12-10)
    # ======================================================

    WS_METRICS_ENABLED = True
    WS_HEALTH_INTERVAL = 30.0
    WS_DIAGNOSTIC_HISTORY = 10
    WS_MAX_DIAGNOSTICS = 50
    WS_ENABLE_RUNTIME_CONFIG = True

    # ======================================================
    # DESKTOP CLIENT (P13-01)
    # ======================================================

    CLIENT_API_URL = "http://localhost:8000"
    CLIENT_WS_URL = "ws://localhost:8000/api/v1/ws"
    CLIENT_TIMEOUT = 30.0
    CLIENT_RETRY_COUNT = 3
    CLIENT_HEARTBEAT = 30.0
    CLIENT_AUTO_RECONNECT = True
    CLIENT_LOG_LEVEL = "INFO"

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
