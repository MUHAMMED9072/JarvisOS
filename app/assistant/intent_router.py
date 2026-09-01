"""Intent classification and execution routing for the assistant runtime.

The pipeline for every request is::

    text
      -> NaturalLanguageParser   (regex parser -> ParsedRequest)
      -> IntentClassifier        (route assignment -> IntentClassification)
      -> ExecutionRouter         (tool / agent / build / memory /
                                  knowledge / desktop / time / AI)

The AI router is the **last** route: only requests that no deterministic
classifier matches (``conversation``) reach the LLM.  Everything else
executes natively through the JARVIS OS subsystems.
"""

from __future__ import annotations

import datetime as _datetime
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import quote_plus

from app.core.logger import JarvisLogger
from app.agents.base import AgentStatus
from app.desktop.control import SAFE_KEY_NAMES
from app.tools.desktop_tool import DesktopTool as _DesktopTool

from .natural import Intent, detect_natural_intent
from .tool_selector import ToolIntent, detect_tool_intent

ROUTE_AGENT = "agent"
ROUTE_AGENT_CREATE = "agent_create"
ROUTE_AGENT_CTRL = "agent_ctrl"
ROUTE_BROWSER = "browser"
ROUTE_BUILD = "build"
ROUTE_COMMAND = "command"
ROUTE_CONVERSATION = "conversation"
ROUTE_DESKTOP = "desktop"
ROUTE_EVOLVE = "evolve"
ROUTE_OBJECTIVE = "objective"
ROUTE_KNOWLEDGE = "knowledge"
ROUTE_MEMORY = "memory"
ROUTE_MISSION = "mission"
ROUTE_PLAN = "plan"
ROUTE_TIME = "time"
ROUTE_SEO = "seo"
ROUTE_TOOL = "tool"

_AGENT_TYPE_PATTERN = re.compile(
    r"\b(system|tool|development|domain|composite)\s*agent\b",
    re.IGNORECASE,
)

MAX_REPLY_CHARS: int = 4000

# Session lifecycle states for agent instances (P21-27).
AGENT_STATE_READY = "ready"
AGENT_STATE_RUNNING = "running"
AGENT_STATE_PAUSED = "paused"
AGENT_STATE_STOPPED = "stopped"
AGENT_STATE_COMPLETED = "completed"
AGENT_STATE_FAILED = "failed"

_AGENT_LOG_LIMIT: int = 50


def _new_agent_state(note: str = "") -> dict[str, Any]:
    """Session runtime state for one agent instance."""
    state: dict[str, Any] = {
        "status": AGENT_STATE_READY,
        "runs": 0,
        "created": time.time(),
        "last_start": 0.0,
        "last_end": 0.0,
        "last_error": "",
        "last_message": "",
        "logs": [],
    }
    if note:
        _append_agent_log(state, note)
    return state


def _append_agent_log(state: dict[str, Any], message: str) -> None:
    stamp = _datetime.datetime.now().strftime("%H:%M:%S")
    state["logs"].append(f"[{stamp}] {message}")
    if len(state["logs"]) > _AGENT_LOG_LIMIT:
        del state["logs"][:-_AGENT_LOG_LIMIT]

# ---------------------------------------------------------------------------
# Classification records
# ---------------------------------------------------------------------------


@dataclass
class ParsedRequest:
    """A deterministic parse of a natural-language request."""

    route: str
    target: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    source: str = ""


@dataclass
class IntentClassification:
    """The route decision for one request."""

    route: str
    target: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    source: str = ""

    def is_conversation(self) -> bool:
        return self.route == ROUTE_CONVERSATION


# ---------------------------------------------------------------------------
# Pattern tables
# ---------------------------------------------------------------------------

_SITES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "twitter": "https://twitter.com",
    "linkedin": "https://www.linkedin.com",
    "facebook": "https://www.facebook.com",
    "stackoverflow": "https://stackoverflow.com",
    "wikipedia": "https://www.wikipedia.org",
    "reddit": "https://www.reddit.com",
    "amazon": "https://www.amazon.com",
}

# Application names the desktop tool can launch/close (shared with the
# tool so the parser and executor agree on naming).
_APP_NAMES: set[str] = set(_DesktopTool._ALIASES) | set(_DesktopTool._APPS)

_BUILD_ARTIFACTS = (
    "api",
    "app",
    "application",
    "project",
    "script",
    "program",
    "tool",
    "website",
    "web app",
    "cli",
    "module",
    "package",
    "function",
    "class",
    "pipeline",
    "calculator",
    "bot",
    "library",
    "game",
    "server",
    "service",
    "endpoint",
    "dockerfile",
    "plugin",
    "extension",
    "template",
    "database",
    "dashboard",
    "crawler",
    "scraper",
    "framework",
    "rest api",
)

_MATH_ONLY = re.compile(r"^[0-9\s+\-*/%().,]*[0-9][0-9\s+\-*/%().,]*$")


def _is_math_expression(value: str) -> bool:
    return bool(_MATH_ONLY.match(value))


def _is_artifact_request(value: str) -> bool:
    lowered = value.lower()
    return any(artifact in lowered for artifact in _BUILD_ARTIFACTS)


def _match_first(patterns: list[tuple[re.Pattern, Any]], text: str):
    for pattern, payload in patterns:
        match = pattern.match(text)
        if match:
            return match, payload
    return None, None


def _desktop_request(action: str, params: dict[str, Any], source: str) -> ParsedRequest:
    """Build a desktop_tool request with the action merged into params."""
    return ParsedRequest(
        route=ROUTE_DESKTOP,
        target="desktop_tool",
        params={"action": action, **params},
        source=source,
    )


_POINT_IN_TEXT = re.compile(r"\(?\s*(\d{1,4})\s*[,;]\s*(\d{1,4})\s*\)?")


def _parse_point(text: str) -> tuple[int, int] | None:
    """Extract an ``(x, y)`` coordinate pair from free text, or None."""
    match = _POINT_IN_TEXT.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _press_keys(phrase: str) -> list[str] | None:
    """Normalize a key phrase ("ctrl+s", "ctrl and s") into safe keys.

    Returns ``None`` when any token is outside the safe key table so
    the router falls through to the AI for unsupported phrases.
    """
    phrase = re.sub(r"\s+key\s*$", "", (phrase or "").strip())
    if not phrase:
        return None
    tokens = re.split(r"\s+(?:and|plus)\s+|\s*\+\s*|\s*,\s*|\s+", phrase.lower())
    tokens = [token for token in tokens if token]
    if not tokens:
        return None
    for token in tokens:
        if token not in SAFE_KEY_NAMES and not (
            len(token) == 1 and token.isprintable()
        ):
            return None
    return tokens


class NaturalLanguageParser:
    """Stateless parser turning free text into a :class:`ParsedRequest`.

    Order matters: more specific patterns (memory, time, file, desktop)
    are checked before the generic build and tool selectors.
    """

    # -- memory (deterministic natural commands first) ------------------
    # Handled by detect_natural_intent: remember / recall / search.

    _TIME_PATTERNS = [
        re.compile(r"^(?:what|what's|what is)(?: the)? time(?: is it| now)?[.!?]?$", re.IGNORECASE),
        re.compile(r"^tell me (?:the |what )(?:time|the time)[.!?]?$", re.IGNORECASE),
        re.compile(r"^what(?:'s| is)? the current time[.!?]?$", re.IGNORECASE),
    ]

    _FORGET_PATTERN = re.compile(r"^forget (?:my |about )?(.+?)(?:\s+from memory)?[.!]?$", re.IGNORECASE)

    # -- calculation (math only -> python_tool) -------------------------
    _CALC_PATTERN = re.compile(r"^(?:calculate|compute|eval(?:uate)?)\s+(.+)$", re.IGNORECASE)
    _WHAT_CALC_PATTERN = re.compile(r"^what(?:'s| is)? (.+?)[.!]?$", re.IGNORECASE)

    # -- file operations -------------------------------------------------
    _OPEN_FILE = re.compile(r"^open (?:the |this |that )?file (.+)$", re.IGNORECASE)
    _OPEN_FOLDER = re.compile(r"^(?:open|show) (?:the )?(?:folder|directory|dir) (.+)$", re.IGNORECASE)
    _MKDIR = re.compile(r"^(?:create|make|new) (?:a |the )?(?:folder|directory|dir) (.+)$", re.IGNORECASE)
    _DELETE = re.compile(r"^(?:delete|remove) (?:the )?(?:file |folder |directory |dir )?(.+)$", re.IGNORECASE)
    _RENAME = re.compile(r"^rename (.+) (?:to|as) (.+)$", re.IGNORECASE)
    _COPY = re.compile(r"^copy (.+) (?:to|into) (.+)$", re.IGNORECASE)
    _MOVE = re.compile(r"^move (.+) (?:to|into) (.+)$", re.IGNORECASE)
    _LIST_FILES = re.compile(r"^list (?:the )?(?:files|contents)(?: in| of| under)? (.+)$", re.IGNORECASE)
    _LIST_FILES_CWD = re.compile(r"^list (?:the )?(?:files|contents)[.!]?$", re.IGNORECASE)

    # -- desktop / power -------------------------------------------------
    _OPEN_APP = re.compile(r"^(?:open|launch|start|run)\s+(?:the\s+)?(.+?)[.!]?$", re.IGNORECASE)
    _CLOSE_APP = re.compile(r"^(?:close|quit|exit|kill|terminate)\s+(?:the\s+)?(.+?)[.!]?$", re.IGNORECASE)
    _SHUTDOWN = re.compile(
        r"^(?:shutdown|shut down|turn off|power off)(?: the)?(?: computer| pc| system| machine)?"
        r"(?: in (\d+) (second|minute|hour)s?)?[.!]?$",
        re.IGNORECASE,
    )
    _RESTART = re.compile(
        r"^(?:restart|reboot)(?: the)?(?: computer| pc| system| machine)?"
        r"(?: in (\d+) (second|minute|hour)s?)?[.!]?$",
        re.IGNORECASE,
    )
    _SLEEP = re.compile(r"^(?:sleep|go to sleep|put (?:the )?(?:computer|pc) to sleep)[.!]?$", re.IGNORECASE)
    _HIBERNATE = re.compile(r"^(?:hibernate|put (?:the )?(?:computer|pc) into hibernation)[.!]?$", re.IGNORECASE)
    _LOCK = re.compile(r"^lock(?: the)?(?: screen| computer| pc| workstation)?[.!]?$", re.IGNORECASE)
    _LOGOUT = re.compile(r"^(?:log ?out|log ?off|sign ?out|sign ?off)(?: of)?(?: the)?(?: computer| system| session)?[.!]?$", re.IGNORECASE)

    # -- desktop / media -------------------------------------------------
    _VOLUME_SET = re.compile(
        r"^(?:set|change|adjust)\s+(?:the\s+)?volume\s+(?:to|at)\s+(\d{1,3})\s*(?:percent|%|pct)?[.!]?$",
        re.IGNORECASE,
    )
    _VOLUME_UP = re.compile(
        r"^(?:(?:turn|set|bump)\s+up\s+(?:the\s+)?volume|(?:turn|set|bump)?\s*(?:the\s+)?volume\s+up)"
        r"(?:\s+by\s+(\d{1,3})\s*(?:percent|%|pct)?)?[.!]?$",
        re.IGNORECASE,
    )
    _VOLUME_DOWN = re.compile(
        r"^(?:(?:turn|set|bump)\s+down\s+(?:the\s+)?volume|(?:turn|set|bump)?\s*(?:the\s+)?volume\s+down)"
        r"(?:\s+by\s+(\d{1,3})\s*(?:percent|%|pct)?)?[.!]?$",
        re.IGNORECASE,
    )
    _MUTE = re.compile(r"^(?:mute|turn\s+(?:the\s+)?volume\s+off)(?:\s+the\s+volume)?[.!]?$", re.IGNORECASE)
    _UNMUTE = re.compile(r"^(?:unmute|turn\s+(?:the\s+)?volume\s+back\s+on)[.!]?$", re.IGNORECASE)
    _BRIGHTNESS_SET = re.compile(
        r"^(?:set|change|adjust)\s+(?:the\s+)?(?:screen|display\s+)?\s*brightness\s+(?:to|at)\s+(\d{1,3})\s*(?:percent|%|pct)?[.!]?$",
        re.IGNORECASE,
    )
    _BRIGHTNESS_UP = re.compile(
        r"^(?:make\s+(?:the\s+)?(?:screen\s+)?brighter|turn\s+(?:the\s+)?(?:screen\s+)?brightness\s+up)"
        r"(?:\s+by\s+(\d{1,3})\s*(?:percent|%|pct)?)?[.!]?$",
        re.IGNORECASE,
    )
    _BRIGHTNESS_DOWN = re.compile(
        r"^(?:make\s+(?:the\s+)?(?:screen\s+)?dimmer|turn\s+(?:the\s+)?(?:screen\s+)?brightness\s+down)"
        r"(?:\s+by\s+(\d{1,3})\s*(?:percent|%|pct)?)?[.!]?$",
        re.IGNORECASE,
    )
    _EXPLORE_FOLDER = re.compile(
        r"^(?:explore|browse|open\s+in\s+(?:the\s+)?(?:file\s+)?explorer|show\s+in\s+(?:file\s+)?explorer)"
        r"\s+(?:the\s+)?(?:folder|directory|dir)?\s*(.+)$",
        re.IGNORECASE,
    )
    _SCREENSHOT = re.compile(
        r"^(?:take\s+(?:a\s+)?screenshot|screen\s*shot|capture\s+(?:the\s+)?screen)[.!]?$",
        re.IGNORECASE,
    )
    # P30 desktop control: mouse / keyboard / window patterns (generic,
    # no per-application hardcoding).
    _CLICK_AT = re.compile(
        r"^(?:click|tap|left[- ]?click)(?:\s+at)?(?:\s+on)?\s+"
        r"(?:(?:the\s+)?point\s*)?(.+?)[.!]?$",
        re.IGNORECASE,
    )
    _DOUBLE_CLICK_AT = re.compile(
        r"^double[- ]?click(?:\s+at)?(?:\s+on)?\s+"
        r"(?:(?:the\s+)?point\s*)?(.+?)[.!]?$",
        re.IGNORECASE,
    )
    _RIGHT_CLICK_AT = re.compile(
        r"^right[- ]?click(?:\s+at)?(?:\s+on)?\s+"
        r"(?:(?:the\s+)?point\s*)?(.+?)[.!]?$",
        re.IGNORECASE,
    )
    _CLICK_PLAIN = re.compile(
        r"^(?:click|tap|left[- ]?click|double[- ]?click|right[- ]?click)(?:\s+at)?(?:\s+(?:the\s+)?cursor)?\s*(?:point)?[.!]?$",
        re.IGNORECASE,
    )
    _MOUSE_MOVE = re.compile(
        r"^move\s+(?:the\s+)?(?:mouse|cursor|pointer)\s+to\s+(?:(?:the\s+)?point\s+)?(.+?)[.!]?$",
        re.IGNORECASE,
    )
    _DRAG = re.compile(
        r"^drag\s+from\s+(?:the\s+)?point\s+(.+?)\s+to\s+(?:the\s+)?point\s+(.+?)[.!]?$",
        re.IGNORECASE,
    )
    _SCROLL = re.compile(
        r"^scroll(?:\s+(?:the\s+)?(?:mouse\s+)?(?:wheel)?)?(?:\s+(up|down))?"
        r"(?:\s+by\s+(\d{1,3}))?(?:\s+times)?(?:,\s*(up|down))?[.!]?$",
        re.IGNORECASE,
    )
    _TYPE_TEXT = re.compile(r"^(?:type(?: out)?|enter)\s+(.+?)[.!]?$", re.IGNORECASE)
    _PRESS_KEY = re.compile(r"^press\s+(?:the\s+)?(.+?)[.!]?$", re.IGNORECASE)
    _LIST_WINDOWS = re.compile(
        r"^(?:show|list)\s+(?:me\s+)?(?:the\s+)?(?:open\s+)?windows?(?:\s+now)?[.!]?$",
        re.IGNORECASE,
    )
    _WHAT_WINDOWS = re.compile(
        r"^(?:what|which)\s+windows?\s+are\s+(?:currently\s+)?open[.!]?$",
        re.IGNORECASE,
    )
    _FOCUS_WINDOW = re.compile(
        r"^focus\s+(?:the\s+)?(?:window\s+)?([^.!]*?)[.!]?$", re.IGNORECASE
    )
    _MINIMIZE_WINDOW = re.compile(
        r"^minimize\s+(?:the\s+)?(?:window\s+)?([^.!]*?)[.!]?$", re.IGNORECASE
    )
    _MAXIMIZE_WINDOW = re.compile(
        r"^maximize\s+(?:the\s+)?(?:window\s+)?([^.!]*?)[.!]?$", re.IGNORECASE
    )
    _RESTORE_WINDOW = re.compile(
        r"^restore\s+(?:the\s+)?(?:window\s+)?([^.!]*?)[.!]?$", re.IGNORECASE
    )
    _CLOSE_WINDOW = re.compile(
        r"^close\s+(?:the\s+|this\s+)?window(?:\s+([^.!]*?))?[.!]?$", re.IGNORECASE
    )
    _CLOSE_NAMED_WINDOW = re.compile(
        r"^close\s+(?:the\s+|this\s+)?([^.!]+?)\s+window[.!]?$", re.IGNORECASE
    )
    _WHATSAPP_SEND = re.compile(
        r"^(?:send\s+(?:a\s+)?whatsapp\s+(?:message\s+)?to|whatsapp)\s+(.+?)(?:\s+saying|\s+stating|\s+with\s+message|\s+message)?[:\s]+(.+)$",
        re.IGNORECASE,
    )

    # -- browser ---------------------------------------------------------
    _GOOGLE_SEARCH = re.compile(r"^(?:google(?: search)?|search (?:on |in )?google)(?: for)? (.+?)[.!]?$", re.IGNORECASE)
    _SEARCH_WEB = re.compile(r"^(?:search|look up) (?:the )?web for (.+?)[.!]?$", re.IGNORECASE)
    _OPEN_SITE = re.compile(r"^open (?:the |this |that )?(?:website|site|page|url) (.+)$", re.IGNORECASE)
    _OPEN_DOMAIN = re.compile(
        r"^open ([a-z0-9][a-z0-9\-]*\.(?:com|org|net|io|dev|ai|edu|gov|me|co|app|xyz)(?:[/:?#][^\s]*)?)$",
        re.IGNORECASE,
    )
    _OPEN_FULL_URL = re.compile(r"^open (https?://[^\s]+)$", re.IGNORECASE)

    # -- SEO -----------------------------------------------------------
    _SEO_AUDIT = re.compile(
        r"^(?:jarvis[,\s])?(?:audit|analyze?\s+seo)(?:\s+of)?\s?(https?://[^\s]+)?$",
        re.IGNORECASE,
    )
    _SEO_AUDIT_DOMAIN = re.compile(
        r"^(?:jarvis[,\s])?analyze?\s+seo\s+of\s+(.+)$", re.IGNORECASE,
    )
    _SEO_KEYWORD_RESEARCH = re.compile(
        r"^(?:jarvis[,\s])?research\s+keywords(?:\s+for\s+)?(.+)$", re.IGNORECASE,
    )
    _SEO_FIND_CONTENT_GAPS = re.compile(
        r"^(?:jarvis[,\s])?find\s+content\s+gaps?$", re.IGNORECASE,
    )
    _SEO_ANALYZE_COMPETITORS = re.compile(
        r"^(?:jarvis[,\s])?analyze\s+competitors?", re.IGNORECASE,
    )

    # -- git -------------------------------------------------------------
    _GIT_PATTERNS: list[tuple[re.Pattern, dict[str, Any]]] = [
        (re.compile(r"^(?:git )?commit(?: changes)?(?: -m[\s:]+)?(.+)?$", re.IGNORECASE), {"action": "commit", "message": None}),
        (re.compile(r"^(?:git )?push(?: to (?:origin|remote))?$", re.IGNORECASE), {"action": "push"}),
        (re.compile(r"^(?:git )?pull(?: from (?:origin|remote))?$", re.IGNORECASE), {"action": "pull"}),
        (re.compile(r"^(?:git )?branch$", re.IGNORECASE), {"action": "branch"}),
        (re.compile(r"^(?:git )?merge (.+)$", re.IGNORECASE), {"action": "merge", "target_branch": None}),
        (re.compile(r"^(?:show|check) (?:git )?status$", re.IGNORECASE), {"action": "status"}),
        (re.compile(r"^(?:git )?status$", re.IGNORECASE), {"action": "status"}),
        (re.compile(r"^(?:git )?add (.+)$", re.IGNORECASE), {"action": "add", "paths": None}),
        (re.compile(r"^(?:git )?log$", re.IGNORECASE), {"action": "log"}),
    ]

    # -- shell -----------------------------------------------------------
    _SHELL_DIRECT = re.compile(r"^(ping|ipconfig|netstat|whoami|hostname|tasklist|systeminfo|dir|ls)(?:\s+(.+))?[.!]?$", re.IGNORECASE)
    _COMMAND_VERB = re.compile(r"^(?:run|execute) (?:the |a )?command[: ]+(.+)$", re.IGNORECASE)

    # -- knowledge graph -------------------------------------------------
    _KNOWLEDGE_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"^(?:show|list) (?:the |my )?entities[.!]?$", re.IGNORECASE), "entities"),
        (re.compile(r"^(?:show|list) (?:the |my )?capabilities[.!]?$", re.IGNORECASE), "capabilities"),
        (re.compile(r"^show (?:the )?relationships?(?: in (?:the )?(?:knowledge graph|graph))?[.!]?$", re.IGNORECASE), "relationships"),
        (re.compile(r"^(?:show|describe) (?:the )?(?:knowledge graph|knowledge base)(?: summary)?[.!]?$", re.IGNORECASE), "summary"),
    ]

    # -- task / execution status ----------------------------------------
    _TASKS_PATTERNS: list[re.Pattern] = [
        re.compile(r"^(?:(?:show|list|view)\s+)?(?:recent\s+|my\s+)?(?:tasks|executions|task status)[.!]?$", re.IGNORECASE),
        re.compile(r"^what\s+tasks?\s+are\s+(?:running|active|pending|queued)[.!]?$", re.IGNORECASE),
    ]

    # -- agents ----------------------------------------------------------
    _AGENT_PATTERN = re.compile(r"^(?:run|ask|call|use|invoke|delegate to|send to) (?:the )?agent (.+?)[.!]?$", re.IGNORECASE)

    # Delegation phrasing with the name before "agent" ("use my SEO
    # agent to audit my website", "ask the research agent for news").
    _AGENT_USE_PATTERNS: list[re.Pattern] = [
        re.compile(r"^(?:use|ask)\s+(?:my|the)\s+agent\s+(.+?)\s+(?:to|for)\s+(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^(?:use|ask)\s+(?:my|the)\s+(.+?)\s+agent\s+(?:to|for)\s+(.+?)[.!]?$", re.IGNORECASE),
    ]

    # -- agent creation --------------------------------------------------
    _AGENT_CREATE_PATTERNS: list[re.Pattern] = [
        re.compile(r"^create\s+(?:an? |a |the )?(?:\w+\s+){0,2}?agent\s*(?:to|that|which|named|called|for)?\s*(.*)$", re.IGNORECASE),
        re.compile(r"^(?:make|build|generate|write|design)\s+(?:an? |a |the )?(?:\w+\s+){0,2}?agent\s*(?:to|that|which|named|called|for)?\s*(.*)$", re.IGNORECASE),
    ]

    # -- agent control (session lifecycle: pause/resume/stop/delete/
    #    status/logs).  Anchored to the "agent" keyword so bare
    #    "pause", "resume" or "stop" never match.
    _AGENT_CTRL_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"^pause\s+(?:the\s+)?agent\s+(.+?)[.!]?$", re.IGNORECASE), "pause"),
        (re.compile(r"^resume\s+(?:the\s+)?agent\s+(.+?)[.!]?$", re.IGNORECASE), "resume"),
        (re.compile(r"^stop\s+(?:the\s+)?agent\s+(.+?)[.!]?$", re.IGNORECASE), "stop"),
        (re.compile(r"^delete\s+(?:the\s+)?agent\s+(.+?)[.!]?$", re.IGNORECASE), "delete"),
        (re.compile(r"^agent\s+status(?:\s+of)?\s+(.+?)[.!]?$", re.IGNORECASE), "status"),
        (re.compile(r"^(?:show\s+)?status\s+of\s+(?:the\s+)?agent\s+(.+?)[.!]?$", re.IGNORECASE), "status"),
        (re.compile(r"^agent\s+logs(?:\s+of)?\s+(.+?)[.!]?$", re.IGNORECASE), "logs"),
        (re.compile(r"^(?:show\s+)?logs?\s+of\s+(?:the\s+)?agent\s+(.+?)[.!]?$", re.IGNORECASE), "logs"),
    ]

    # -- mission control (start / pause / resume / cancel / status).
    #    Anchored to the "mission" keyword so ordinary verbs ("launch
    #    the app", "cancel", "pause the music") never match.  The
    #    approval gate resolves bare "approve"/"cancel" phrases first,
    #    so "cancel mission X" only reaches here when no proposal is
    #    pending.
    _MISSION_START_PATTERNS: list[re.Pattern] = [
        re.compile(r"^(?:start|create|launch|begin|run|new)\s+(?:a\s+|the\s+)?mission\s+(?:to\s+|for\s+|:\s*)(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^mission\s*:\s*(.+?)[.!]?$", re.IGNORECASE),
    ]
    _MISSION_CTRL_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"^pause\s+(?:the\s+)?mission(?:\s+(\S+))?[.!]?$", re.IGNORECASE), "pause"),
        (re.compile(r"^resume\s+(?:the\s+)?mission(?:\s+(\S+))?[.!]?$", re.IGNORECASE), "resume"),
        (re.compile(r"^cancel\s+(?:the\s+)?mission(?:\s+(\S+))?[.!]?$", re.IGNORECASE), "cancel"),
        (re.compile(r"^(?:abort|stop)\s+(?:the\s+)?mission(?:\s+(\S+))?[.!]?$", re.IGNORECASE), "cancel"),
        (re.compile(r"^mission\s+status(?:\s+(?:of\s+)?(\S+))?[.!]?$", re.IGNORECASE), "status"),
        (re.compile(r"^(?:show\s+)?status\s+of\s+(?:the\s+)?mission(?:\s+(\S+))?[.!]?$", re.IGNORECASE), "status"),
    ]
    _MISSION_LIST_PATTERNS: list[re.Pattern] = [
        re.compile(r"^(?:list|show|view)\s+(?:my\s+|all\s+|active\s+)?missions[.!]?$", re.IGNORECASE),
        re.compile(r"^what\s+missions?\s+(?:are|is)\s+(?:running|active|pending)[.!?]?$", re.IGNORECASE),
    ]

    # -- autonomous objectives (P32 — self-upgrading workflow).  The
    #    objective route wins before evolution/memory; agent-focused
    #    phrasing stays with agent-creation so capability gaps there
    #    are handled by the agent-creation approval chain instead.
    _OBJECTIVE_PATTERNS: list[re.Pattern] = [
        re.compile(r"^(?:figure|work)\s+out\s+how\s+to\s+do\s+this\s+(?:yourself|on your own)[.!]?$", re.IGNORECASE),
        re.compile(r"^(?:figure|work)\s+out\s+how\s+to\s+(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^learn\s+how\s+to\s+(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^teach\s+yourself\s+(?:how\s+to\s+)?(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^(?:add|gain)\s+(?:the\s+)?(?:ability|capability)\s+to\s+(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^build\s+whatever\s+(?:capabilit(?:y|ies)|tools?)\s+(?:you|jarvis)\s+need\s+(?:to|for)\s+(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^(?:figure|work)\s+out\s+a\s+way\s+to\s+(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^(?:create|build|add)\s+(?:a\s+|an\s+|the\s+)?capability\s+(?:that|to|for)\s+(.+?)[.!]?$", re.IGNORECASE),
        re.compile(r"^handle\s+this\s+(?:yourself|on\s+your\s+own)\s*[.!]?$", re.IGNORECASE),
    ]

    # -- evolution / self-improvement ------------------------------------
    _EVOLVE_PATTERNS: list[re.Pattern] = [
        re.compile(r"^upgrade\s+(?:yourself|you|the system|the codebase|the project|jarvis)[.!]?$", re.IGNORECASE),
        re.compile(r"^improve\s+(?:yourself|you|the system|the codebase|the project|your code|your capabilities)[.!]?$", re.IGNORECASE),
        re.compile(r"^self[- ]?improv(?:e|ement)[.!]?$", re.IGNORECASE),
        re.compile(r"^self[- ]?evol(?:ve|ution)[.!]?$", re.IGNORECASE),
        re.compile(r"^evolve(?: yourself)?[.!]?$", re.IGNORECASE),
        re.compile(r"^start\s+(?:a\s+)?(?:self[- ]?evol(?:ve|ution)|evolution)[.!]?$", re.IGNORECASE),
        re.compile(r"^suggest\s+(?:self[- ]?)?improvements?[.!]?$", re.IGNORECASE),
        re.compile(r"^analyze\s+(?:the\s+)?(?:project|codebase|system)(?:\s+for\s+(?:improvements|weaknesses))?[.!]?$", re.IGNORECASE),
        re.compile(r"^how\s+(?:can|could)\s+you\s+(?:improve|upgrade)(?:\s+yourself)?[.!]?$", re.IGNORECASE),
        # -- self-scan / upgrade-finding ("scan yourself and find where
        #    needed the upgrade?", "find what needs upgrading", ...).
        #    Anchored to self / project targets so bare "scan", "analyze"
        #    or "upgrade" never trigger evolution on their own.
        re.compile(r"^(?:scan|self[- ]?scan|analyze|audit)\s+(?:yourself|the (?:project|codebase|system))[.!?]?$", re.IGNORECASE),
        re.compile(r"^(?:scan|self[- ]?scan|analyze|audit)\s+(?:yourself|the (?:project|codebase|system))\s+(?:for|and\s+find)\s+(?:needed\s+|any\s+)?(?:upgrades?|improvements?)[.!?]?$", re.IGNORECASE),
        re.compile(r"^(?:scan|self[- ]?scan)\s+(?:yourself|the (?:project|codebase|system))\s+and\s+find\s+(?:where\s+needed\s+the\s+upgrade|what\s+needs\s+upgrading)[.!?]?$", re.IGNORECASE),
        re.compile(r"^find\s+(?:where\s+(?:an\s+)?upgrade\s+is\s+needed|what\s+needs\s+upgrading)[.!?]?$", re.IGNORECASE),
    ]

    # -- planning --------------------------------------------------------
    _PLAN_PATTERNS: list[re.Pattern] = [
        re.compile(r"^plan\s+(.+)$", re.IGNORECASE),
        re.compile(r"^(?:make|create|write|prepare|draft|give me)\s+(?:a |an |the )?plan\s+(?:to|for|of)?\s*(.+)$", re.IGNORECASE),
        re.compile(r"^(?:make|create|design|draft)\s+(?:a |an |the )?(?:roadmap|blueprint|architecture|system design)\s+(?:to|for|of|that)?\s*(.+)$", re.IGNORECASE),
        re.compile(r"^automate\s+(.+)$", re.IGNORECASE),
        re.compile(r"^(?:create|set up|build|make)\s+(?:a |an )?(?:workflow|automation)\s+(?:to|for|that)?\s*(.+)$", re.IGNORECASE),
    ]

    # -- build -----------------------------------------------------------
    _BUILD_VERB = re.compile(r"^build\s+(.+)$", re.IGNORECASE)
    _CREATE_VERB = re.compile(r"^(?:create|make|generate)\s+(?:a |an |the )?(.+)$", re.IGNORECASE)

    # -- python scripts --------------------------------------------------
    _SCRIPT_PATTERN = re.compile(r"^(?:run|execute) (?:the |a )?(?:python )?script (.+)$", re.IGNORECASE)

    def parse(self, text: str) -> ParsedRequest | None:
        """Parse *text* into a request, or ``None`` for conversation."""
        stripped = text.strip()
        if not stripped:
            return None

        # Strip optional leading wake-word invocation prefix ("jarvis, what time is it?" -> "what time is it?")
        lowered = stripped.lower()
        for prefix in ("hey jarvis,", "hey jarvis", "jarvis,", "jarvis"):
            if lowered.startswith(prefix) and len(stripped) > len(prefix):
                candidate = stripped[len(prefix):].strip(" ,!.")
                if candidate:
                    stripped = candidate
                break

        # 1. Autonomous objectives ("figure out how to do this
        #    yourself", "learn how to X", "add the ability to X").
        #    Agent-focused phrasing at the START of the request is excluded
        #    so the agent-creation route (and its capability-gap approval
        #    chain) owns it.  Mentions of "agent" later in the request
        #    (e.g. "add the ability to X, create an agent to use it")
        #    do not prevent objective routing — the autonomy workflow
        #    handles both the capability and the agent.
        match = _match_first([(p, True) for p in self._OBJECTIVE_PATTERNS], stripped)
        if match[0] and "agent" not in stripped[:25].lower():
            return ParsedRequest(
                route=ROUTE_OBJECTIVE,
                params={"request": stripped},
                source="objective",
            )

        # 2. Evolution / self-improvement ("scan yourself and find where
        #    needed the upgrade?", "upgrade yourself", "find what needs
        #    upgrading").  Checked before the memory patterns so that
        #    upgrade-finding phrases ("find what needs upgrading") are
        #    routed to the evolution engine instead of a memory search.
        match = _match_first([(p, True) for p in self._EVOLVE_PATTERNS], stripped)
        if match[0]:
            return ParsedRequest(
                route=ROUTE_EVOLVE,
                params={"request": stripped},
                source="evolve",
            )

        # 2. Memory commands (remember / recall / search) win over
        #    everything else ("what is my name" != "what is 2+2").
        intent = detect_natural_intent(stripped)
        if intent is not None and intent.kind in ("remember", "recall", "search_memories"):
            return self._from_natural(intent)

        # 3. Agent control (pause/resume/stop/delete/status/logs) —
        #     checked before file/desktop patterns so "delete agent X",
        #     "pause agent X" or "stop agent X" never fall through to
        #     the file tool or the LLM.  Anchored to the "agent"
        #     keyword.
        match = _match_first(self._AGENT_CTRL_PATTERNS, stripped)
        if match[0]:
            return ParsedRequest(
                route=ROUTE_AGENT_CTRL,
                target=match[1],
                params={"name": match[0].group(1).strip()},
                source="agent-ctrl",
            )

        # 3b. Missions — start a new (approval-gated) mission, control
        #     an existing one, or list them.  Checked before the
        #     desktop patterns so "launch a mission to X" is never read
        #     as an app launch.
        match = _match_first([(p, True) for p in self._MISSION_START_PATTERNS], stripped)
        if match[0]:
            return ParsedRequest(
                route=ROUTE_MISSION,
                target="start",
                params={"goal": match[0].group(1).strip()},
                source="mission-start",
            )
        match = _match_first(self._MISSION_CTRL_PATTERNS, stripped)
        if match[0]:
            ref = match[0].group(1)
            return ParsedRequest(
                route=ROUTE_MISSION,
                target=match[1],
                params={"ref": ref.strip() if ref else ""},
                source="mission-ctrl",
            )
        match = _match_first([(p, True) for p in self._MISSION_LIST_PATTERNS], stripped)
        if match[0]:
            return ParsedRequest(
                route=ROUTE_COMMAND,
                target="missions",
                source="mission-list",
            )

        # 4. Time.
        match = _match_first([(p, True) for p in self._TIME_PATTERNS], stripped)
        if match[0]:
            return ParsedRequest(route=ROUTE_TIME, source="time")

        # 5. Forget.
        match = self._FORGET_PATTERN.match(stripped)
        if match:
            return ParsedRequest(
                route=ROUTE_MEMORY,
                target="forget",
                params={"target": match.group(1).strip()},
                source="forget",
            )

        # 6. Calculation (math only) -> python_tool.
        match = self._CALC_PATTERN.match(stripped)
        if match and _is_math_expression(match.group(1)):
            return self._python_request(f"print({match.group(1).strip()})", "calculate")
        match = self._WHAT_CALC_PATTERN.match(stripped)
        if match and _is_math_expression(match.group(1)):
            return self._python_request(f"print({match.group(1).strip()})", "calculate")

        # 7. Python scripts.
        match = self._SCRIPT_PATTERN.match(stripped)
        if match:
            path = match.group(1).strip()
            return self._python_request(f"exec(open({path!r}).read())", "script")

        # 7b. Desktop mouse-move ("move the mouse to (x, y)") — must win
        #     over the file "move X to Y" pattern.
        match = self._MOUSE_MOVE.match(stripped)
        if match:
            point = _parse_point(match.group(1))
            if point is not None:
                return _desktop_request(
                    "mouse_move", {"x": point[0], "y": point[1]}, "desktop-mouse"
                )

        # 8. File operations.
        file_request = self._parse_file(stripped)
        if file_request is not None:
            return file_request

        # 9. Desktop / power.
        desktop = self._parse_desktop(stripped)
        if desktop is not None:
            return desktop

        # 10. Browser.
        browser = self._parse_browser(stripped)
        if browser is not None:
            return browser

        # 11. Git.
        git_match, git_params = _match_first(self._GIT_PATTERNS, stripped)
        if git_match:
            params = dict(git_params)
            if git_match.groups():
                value = git_match.group(1).strip() if git_match.group(1) else ""
                for key in ("message", "target_branch", "paths"):
                    if key in params and params[key] is None and value:
                        params[key] = value
                        break
            return ParsedRequest(
                route=ROUTE_TOOL,
                target="git_tool",
                params=params,
                source="git",
            )

        # 12. Shell.
        match = self._SHELL_DIRECT.match(stripped)
        if match:
            command = match.group(0).rstrip(".!")
            return ParsedRequest(
                route=ROUTE_TOOL,
                target="shell_tool",
                params={"command": command},
                source="shell-direct",
            )
        match = self._COMMAND_VERB.match(stripped)
        if match:
            return ParsedRequest(
                route=ROUTE_TOOL,
                target="shell_tool",
                params={"command": match.group(1).strip()},
                source="shell-command",
            )

        # 13. Knowledge graph.
        kg_match, kg_action = _match_first(self._KNOWLEDGE_PATTERNS, stripped)
        if kg_match:
            return ParsedRequest(
                route=ROUTE_KNOWLEDGE,
                target=kg_action,
                source="knowledge",
            )

        # 14. Task / execution status ("show tasks", "show recent
        #      executions", "what tasks are running").
        match = _match_first([(p, True) for p in self._TASKS_PATTERNS], stripped)
        if match[0]:
            return ParsedRequest(
                route=ROUTE_COMMAND,
                target="tasks",
                source="tasks",
            )

        # 15. Agents (validated against registered names by the classifier).
        for pattern in self._AGENT_USE_PATTERNS:
            use_match = pattern.match(stripped)
            if use_match:
                return ParsedRequest(
                    route=ROUTE_AGENT,
                    target=use_match.group(1).strip(),
                    params={"request": use_match.group(2).strip()},
                    source="agent-use",
                )
        match = self._AGENT_PATTERN.match(stripped)
        if match:
            target = match.group(1).strip()
            name, _, request = target.partition(" ")
            return ParsedRequest(
                route=ROUTE_AGENT,
                target=name,
                params={"request": request.strip()},
                source="agent",
            )

        # Agent name at start followed by command: "ProjectInspector, execute ..."
        agent_cmd_pattern = re.compile(
            r'^([\w\s]+?),\s*(execute|run|ask|call|use|invoke|check)\s+(.+?)[.!]?$',
            re.IGNORECASE,
        )
        agent_cmd_match = agent_cmd_pattern.match(stripped)
        if agent_cmd_match:
            agent_name = agent_cmd_match.group(1).strip()
            command = agent_cmd_match.group(2).strip()
            request = agent_cmd_match.group(3).strip()
            return ParsedRequest(
                route=ROUTE_AGENT,
                target=agent_name,
                params={"request": request},
                source="agent",
            )

        # 16. Agent creation (create an agent ...) — approval-gated.
        match = _match_first(
            [(p, True) for p in self._AGENT_CREATE_PATTERNS], stripped
        )
        if match[0]:
            return ParsedRequest(
                route=ROUTE_AGENT_CREATE,
                params={"request": match[0].group(1).strip()},
                source="agent-create",
            )

        # 17. Planning ("plan X", "automate X", "roadmap for X", ...).
        match = _match_first([(p, True) for p in self._PLAN_PATTERNS], stripped)
        if match[0]:
            return ParsedRequest(
                route=ROUTE_PLAN,
                params={"request": match[0].group(1).strip()},
                source="plan",
            )

        # 18. Build requests (plan-first: proposals require approval).
        match = self._BUILD_VERB.match(stripped)
        if match:
            return ParsedRequest(
                route=ROUTE_BUILD,
                params={"request": match.group(1).strip(), "plan_first": True},
                source="build-verb",
            )
        match = self._CREATE_VERB.match(stripped)
        if match and _is_artifact_request(match.group(1)):
            return ParsedRequest(
                route=ROUTE_BUILD,
                params={"request": match.group(1).strip(), "plan_first": True},
                source="build-create",
            )

        # 19. Deterministic meta commands (list tools / agents / providers).
        if intent is not None and intent.kind in ("list_tools", "list_agents", "list_providers"):
            return ParsedRequest(
                route=ROUTE_COMMAND,
                target=intent.kind.replace("list_", ""),
                source="natural-list",
            )

        # 18. Existing tool selector (read/write/clone/rest/run python...).
        tool_intent = detect_tool_intent(stripped)
        if tool_intent is not None:
            return self._from_tool_intent(tool_intent)

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _python_request(self, source: str, source_name: str) -> ParsedRequest:
        return ParsedRequest(
            route=ROUTE_TOOL,
            target="python_tool",
            params={"source": source},
            source=source_name,
        )

    def _from_natural(self, intent: Intent) -> ParsedRequest:
        if intent.kind == "remember":
            return ParsedRequest(
                route=ROUTE_MEMORY,
                target="remember",
                params={"predicate": intent.params.get("predicate", "note"), "value": intent.params.get("value", "")},
                source="natural-remember",
            )
        if intent.kind == "search_memories":
            return ParsedRequest(
                route=ROUTE_MEMORY,
                target="search",
                params={"query": intent.params.get("query", "")},
                source="natural-search",
            )
        return ParsedRequest(
            route=ROUTE_MEMORY,
            target="recall",
            params=dict(intent.params),
            source="natural-recall",
        )

    def _from_tool_intent(self, intent: ToolIntent) -> ParsedRequest:
        return ParsedRequest(
            route=ROUTE_TOOL,
            target=intent.tool,
            params=dict(intent.params),
            source="tool-selector",
        )

    def _parse_file(self, text: str) -> ParsedRequest | None:
        def request(action: str, params: dict[str, Any]) -> ParsedRequest:
            params.setdefault("action", action)
            return ParsedRequest(
                route=ROUTE_TOOL,
                target="file_tool",
                params=params,
                source="file",
            )

        match = self._OPEN_FILE.match(text)
        if match:
            return request("read", {"path": match.group(1).strip()})

        match = self._OPEN_FOLDER.match(text)
        if match:
            return request("list", {"path": match.group(1).strip()})

        match = self._MKDIR.match(text)
        if match:
            return request("mkdir", {"path": match.group(1).strip()})

        match = self._DELETE.match(text)
        if match:
            return request("delete", {"path": match.group(1).strip()})

        match = self._RENAME.match(text)
        if match:
            return request("rename", {"path": match.group(1).strip(), "destination": match.group(2).strip()})

        match = self._COPY.match(text)
        if match:
            return request("copy", {"path": match.group(1).strip(), "destination": match.group(2).strip()})

        match = self._MOVE.match(text)
        if match:
            return request("move", {"path": match.group(1).strip(), "destination": match.group(2).strip()})

        match = self._LIST_FILES.match(text)
        if match:
            return request("list", {"path": match.group(1).strip()})

        match = self._LIST_FILES_CWD.match(text)
        if match:
            return request("list", {"path": "."})

        return None

    def _parse_desktop(self, text: str) -> ParsedRequest | None:
        match = self._VOLUME_SET.match(text)
        if match:
            return _desktop_request("set_volume", {"amount": int(match.group(1))}, "desktop-volume")
        match = self._VOLUME_UP.match(text)
        if match:
            params = {"step": int(match.group(1))} if match.group(1) else {}
            return _desktop_request("volume_up", params, "desktop-volume")
        match = self._VOLUME_DOWN.match(text)
        if match:
            params = {"step": int(match.group(1))} if match.group(1) else {}
            return _desktop_request("volume_down", params, "desktop-volume")
        if self._MUTE.match(text):
            return _desktop_request("mute", {}, "desktop-volume")
        if self._UNMUTE.match(text):
            return _desktop_request("unmute", {}, "desktop-volume")

        match = self._BRIGHTNESS_SET.match(text)
        if match:
            return _desktop_request("set_brightness", {"amount": int(match.group(1))}, "desktop-brightness")
        match = self._BRIGHTNESS_UP.match(text)
        if match:
            params = {"step": int(match.group(1))} if match.group(1) else {}
            return _desktop_request("brightness_up", params, "desktop-brightness")
        match = self._BRIGHTNESS_DOWN.match(text)
        if match:
            params = {"step": int(match.group(1))} if match.group(1) else {}
            return _desktop_request("brightness_down", params, "desktop-brightness")

        match = self._EXPLORE_FOLDER.match(text)
        if match:
            return _desktop_request("open_folder", {"path": match.group(1).strip()}, "desktop-open-folder")

        if self._SCREENSHOT.match(text):
            return _desktop_request("screenshot", {}, "desktop-screenshot")

        # -- P30 desktop control: mouse / keyboard / windows -----------
        match = self._CLICK_AT.match(text)
        if match:
            point = _parse_point(match.group(1))
            if point is not None:
                return _desktop_request(
                    "mouse_click", {"x": point[0], "y": point[1]}, "desktop-click"
                )
            return None
        match = self._DOUBLE_CLICK_AT.match(text)
        if match:
            point = _parse_point(match.group(1))
            if point is not None:
                return _desktop_request(
                    "double_click", {"x": point[0], "y": point[1]}, "desktop-click"
                )
            return None
        match = self._RIGHT_CLICK_AT.match(text)
        if match:
            point = _parse_point(match.group(1))
            if point is not None:
                return _desktop_request(
                    "right_click", {"x": point[0], "y": point[1]}, "desktop-click"
                )
            return None
        if self._CLICK_PLAIN.match(text):
            return _desktop_request("mouse_click", {}, "desktop-click")

        match = self._DRAG.match(text)
        if match:
            start = _parse_point(match.group(1))
            end = _parse_point(match.group(2))
            if start is not None and end is not None:
                params = {
                    "x1": start[0], "y1": start[1],
                    "x2": end[0], "y2": end[1],
                }
                return _desktop_request("drag", params, "desktop-drag")
            return None

        match = self._SCROLL.match(text)
        if match:
            direction = match.group(1) or match.group(3) or "down"
            amount = int(match.group(2)) if match.group(2) else 3
            clicks = -amount if direction == "up" else amount
            return _desktop_request(
                "scroll", {"scroll_clicks": clicks}, "desktop-scroll"
            )

        match = self._TYPE_TEXT.match(text)
        if match:
            typed = match.group(1).strip()
            if typed:
                return _desktop_request("type", {"text": typed}, "desktop-type")

        match = self._PRESS_KEY.match(text)
        if match:
            keys = _press_keys(match.group(1))
            if keys is not None:
                if len(keys) == 1:
                    return _desktop_request(
                        "key", {"key": keys[0]}, "desktop-key"
                    )
                return _desktop_request(
                    "hotkey", {"keys": keys}, "desktop-key"
                )
            return None

        if self._LIST_WINDOWS.match(text) or self._WHAT_WINDOWS.match(text):
            return _desktop_request("windows", {}, "desktop-windows")

        window_actions = (
            (self._FOCUS_WINDOW, "focus_window", "desktop-focus"),
            (self._MINIMIZE_WINDOW, "minimize_window", "desktop-minimize"),
            (self._MAXIMIZE_WINDOW, "maximize_window", "desktop-maximize"),
            (self._RESTORE_WINDOW, "restore_window", "desktop-restore"),
        )
        for pattern, action, source in window_actions:
            match = pattern.match(text)
            if match and match.group(1).strip():
                return _desktop_request(
                    action, {"window": match.group(1).strip()}, source
                )

        match = self._CLOSE_WINDOW.match(text)
        if match:
            target = (match.group(1) or "").strip()
            params = {"window": target} if target else {}
            return _desktop_request("close_window", params, "desktop-close-window")
        match = self._CLOSE_NAMED_WINDOW.match(text)
        if match:
            title = match.group(1).strip()
            if title:
                return _desktop_request(
                    "close_window", {"window": title}, "desktop-close-window"
                )

        match = self._WHATSAPP_SEND.match(text)
        if match:
            return _desktop_request(
                "send_whatsapp",
                {"contact": match.group(1).strip(), "message": match.group(2).strip()},
                "desktop-whatsapp",
            )

        match = self._SHUTDOWN.match(text)
        if match:
            return ParsedRequest(
                route=ROUTE_DESKTOP,
                target="desktop_tool",
                params={"action": "shutdown", "delay_seconds": self._delay_from_match(match)},
                source="desktop-shutdown",
            )
        match = self._RESTART.match(text)
        if match:
            return ParsedRequest(
                route=ROUTE_DESKTOP,
                target="desktop_tool",
                params={"action": "restart", "delay_seconds": self._delay_from_match(match)},
                source="desktop-restart",
            )
        if self._SLEEP.match(text):
            return ParsedRequest(route=ROUTE_DESKTOP, target="desktop_tool", params={"action": "sleep"}, source="desktop-sleep")
        if self._HIBERNATE.match(text):
            return ParsedRequest(route=ROUTE_DESKTOP, target="desktop_tool", params={"action": "hibernate"}, source="desktop-hibernate")
        if self._LOCK.match(text):
            return ParsedRequest(route=ROUTE_DESKTOP, target="desktop_tool", params={"action": "lock"}, source="desktop-lock")
        if self._LOGOUT.match(text):
            return ParsedRequest(route=ROUTE_DESKTOP, target="desktop_tool", params={"action": "logout"}, source="desktop-logout")

        match = self._OPEN_APP.match(text)
        if match:
            target = match.group(1).strip().lower()
            if target in _SITES:
                return ParsedRequest(
                    route=ROUTE_BROWSER,
                    target="desktop_tool",
                    params={"action": "open_url", "url": _SITES[target]},
                    source="browser-site",
                )
            if target in _APP_NAMES:
                return ParsedRequest(
                    route=ROUTE_DESKTOP,
                    target="desktop_tool",
                    params={"action": "open_app", "app": target},
                    source="desktop-open",
                )
            # Not an application or site: fall through (e.g. "run python
            # print(1)" is a tool request, not an app launch).
            return None

        match = self._CLOSE_APP.match(text)
        if match:
            target = match.group(1).strip().lower()
            if target in _APP_NAMES:
                return ParsedRequest(
                    route=ROUTE_DESKTOP,
                    target="desktop_tool",
                    params={"action": "close_app", "app": target},
                    source="desktop-close",
                )
            return None

        return None

    def _parse_browser(self, text: str) -> ParsedRequest | None:
        match = self._GOOGLE_SEARCH.match(text)
        if match:
            query = quote_plus(match.group(1).strip())
            return ParsedRequest(
                route=ROUTE_BROWSER,
                target="desktop_tool",
                params={"action": "open_url", "url": f"https://www.google.com/search?q={query}"},
                source="browser-google",
            )
        match = self._SEARCH_WEB.match(text)
        if match:
            query = quote_plus(match.group(1).strip())
            return ParsedRequest(
                route=ROUTE_BROWSER,
                target="desktop_tool",
                params={"action": "open_url", "url": f"https://www.google.com/search?q={query}"},
                source="browser-web",
            )
        match = self._OPEN_FULL_URL.match(text)
        if match:
            return ParsedRequest(
                route=ROUTE_BROWSER,
                target="desktop_tool",
                params={"action": "open_url", "url": match.group(1).strip()},
                source="browser-url",
            )
        match = self._OPEN_DOMAIN.match(text)
        if match:
            return ParsedRequest(
                route=ROUTE_BROWSER,
                target="desktop_tool",
                params={"action": "open_url", "url": match.group(1).strip()},
                source="browser-domain",
            )
        match = self._OPEN_SITE.match(text)
        if match:
            url = match.group(1).strip()
            if url.lower() in _SITES:
                url = _SITES[url.lower()]
            return ParsedRequest(
                route=ROUTE_BROWSER,
                target="desktop_tool",
                params={"action": "open_url", "url": url},
                source="browser-site",
            )
        return None

    @staticmethod
    def _delay_from_match(match: re.Match) -> int:
        if not match.group(1):
            return 0
        value = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "minute":
            return value * 60
        if unit == "hour":
            return value * 3600
        return value


def _normalize_agent_name(name: str) -> str:
    """Lower-case and strip separator noise so ``ProjectInspector``,
    ``project_inspector_agent`` and ``ProjectInspectorAgent`` all match."""

    return (name or "").lower().replace("_", "").replace(" ", "").replace("-", "")


class IntentClassifier:
    """Assigns a route to each request using the :class:`NaturalLanguageParser`."""

    def __init__(self, parser: NaturalLanguageParser | None = None) -> None:
        self._parser = parser or NaturalLanguageParser()

    @property
    def parser(self) -> NaturalLanguageParser:
        return self._parser

    def classify(
        self,
        text: str,
        agent_names: list[str] | tuple[str, ...] = (),
    ) -> IntentClassification:
        """Classify *text* into an :class:`IntentClassification`.

        Unmatched requests are classified as ``conversation`` (the AI
        fallback route).
        """
        request = self._parser.parse(text)
        if request is None:
            return IntentClassification(
                route=ROUTE_CONVERSATION,
                source="fallback",
                confidence=0.0,
            )

        if request.route == ROUTE_AGENT:
            name = _normalize_agent_name(request.target or "")
            matched = None
            for a in agent_names:
                a_norm = _normalize_agent_name(a)
                if a_norm and (name == a_norm or name in a_norm or a_norm in name):
                    matched = a
                    break
            if matched is None:
                # No such agent -> treat as a conversation (AI).
                return IntentClassification(
                    route=ROUTE_CONVERSATION,
                    source="agent-unmatched",
                    confidence=0.0,
                )
            # Resolve to the canonical (registered) name so downstream
            # instance lookup succeeds even when the user writes a longer /
            # differently-punctuated form (e.g. "ProjectInspectorAgent" for
            # the agent registered as "ProjectInspector").
            return IntentClassification(
                route=request.route,
                target=matched,
                params=request.params,
                confidence=0.98,
                source=request.source,
            )

        return IntentClassification(
            route=request.route,
            target=request.target,
            params=request.params,
            confidence=0.98,
            source=request.source,
        )


# ---------------------------------------------------------------------------
# Execution router
# ---------------------------------------------------------------------------


def format_tool_output(name: str, output: Any) -> str:
    """Format a tool's output for display."""
    if isinstance(output, dict):
        import json

        text = json.dumps(output, indent=2, default=str)
    elif isinstance(output, str):
        text = output
    elif output is None:
        return "(no output)"
    else:
        text = str(output)
    return text[:MAX_REPLY_CHARS]


class ExecutionRouter:
    """Executes classified intents against the JARVIS OS subsystems.

    Owns the execution for every non-conversation route: memory, tool,
    desktop, browser, agent, knowledge, build and time.  The AI pipeline
    is deliberately NOT part of this router (conversation stays in the
    assistant runtime, keeping the LLM as the last resort).
    """

    def __init__(
        self,
        *,
        memory: Any | None = None,
        graph: Any | None = None,
        ai: Any | None = None,
        agents: Any | None = None,
        agent_instances: dict[str, Any] | None = None,
        orchestrator: Any | None = None,
        tools: dict[str, Any] | None = None,
        tool_result_sink: Callable[[dict[str, Any]], None] | None = None,
        approval: Any | None = None,
        mission_manager: Any | None = None,
        event_bus: Any | None = None,
        workflow_engine: Any | None = None,
        timeline: Any | None = None,
        goal_manager: Any | None = None,
    ) -> None:
        self._memory = memory
        self._graph = graph
        self._ai = ai
        self._agents = agents
        self._agent_instances = agent_instances if agent_instances is not None else {}
        self._agent_runtime: dict[str, dict[str, Any]] = {}
        self._orchestrator = orchestrator
        self._tools = tools if tools is not None else {}
        self._tool_result_sink = tool_result_sink
        self._approval = approval
        self._mission_manager_override = mission_manager
        self._bus = event_bus
        self._workflow_engine_override = workflow_engine
        self._timeline = timeline
        self._goal_manager = goal_manager

    # ------------------------------------------------------------------
    # Events (P29 — live operations console feeds off these)
    # ------------------------------------------------------------------

    def _publish(self, event: str, **data: Any) -> None:
        """Publish an event on the kernel bus (no-op safe)."""
        if self._bus is None:
            return
        try:
            self._bus.publish(event, **data)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(
        self,
        classification: IntentClassification,
        on_token: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Execute a classified intent and return the result dict."""
        route = classification.route
        if route == ROUTE_MEMORY:
            return self._execute_memory(classification)
        if route in (ROUTE_TOOL, ROUTE_DESKTOP, ROUTE_BROWSER):
            return self._execute_tool(classification)
        if route == ROUTE_AGENT:
            return self._execute_agent(classification)
        if route == ROUTE_AGENT_CTRL:
            return self._control_agent(classification)
        if route == ROUTE_MISSION:
            return self._execute_mission(classification)
        if route == ROUTE_KNOWLEDGE:
            return self._execute_knowledge(classification)
        if route == ROUTE_BUILD:
            if classification.params.get("plan_first"):
                return self._propose_plan(classification.params.get("request", ""))
            return {
                "kind": "build",
                "text": "",
                "request": classification.params.get("request", ""),
            }
        if route == ROUTE_PLAN:
            return self._propose_plan(classification.params.get("request", ""))
        if route == ROUTE_EVOLVE:
            return self._propose_evolve(classification.params.get("request", ""))
        if route == ROUTE_OBJECTIVE:
            return self._execute_objective(classification.params.get("request", ""))
        if route == ROUTE_AGENT_CREATE:
            return self._propose_agent(classification.params.get("request", ""))
        if route == ROUTE_TIME:
            return self._execute_time()
        if route == ROUTE_SEO:
            return self._execute_seo(classification)
        return {"kind": "reply", "text": "I didn't understand that."}

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def _execute_memory(self, classification: IntentClassification) -> dict[str, Any]:
        target = classification.target
        params = classification.params

        if target == "remember":
            return self._remember(params.get("predicate", "note"), params.get("value", ""))

        if target == "recall":
            if params.get("all"):
                return self._recall_all()
            if params.get("search"):
                return self._search_memories(params.get("query", ""))
            predicate = params.get("predicate", "")
            fact = self._recall_fact(predicate)
            if fact:
                return {
                    "kind": "reply",
                    "text": f"You told me that your {predicate} is {fact.obj}.",
                    "data": {"fact": fact.to_dict()},
                }
            return {"kind": "reply", "text": f"I don't have anything recorded about your {predicate} yet."}

        if target == "search":
            return self._search_memories(params.get("query", ""))

        if target == "forget":
            return self._forget(params.get("target", ""))

        return {"kind": "reply", "text": "I didn't understand that."}

    def _remember(self, predicate: str, value: str) -> dict[str, Any]:
        if not value:
            return {"kind": "reply", "text": "What would you like me to remember?"}
        try:
            self._memory.knowledge.add_fact(
                subject="user", predicate=predicate, obj=value, source="user",
            )
        except Exception:  # noqa: BLE001
            pass
        self._memory.remember(
            "user",
            f"Remembered: {predicate} = {value}",
            metadata={"fact": True, "predicate": predicate},
        )
        return {
            "kind": "reply",
            "text": f"Got it — I'll remember your {predicate} is {value}.",
            "data": {"predicate": predicate, "value": value},
        }

    def _recall_fact(self, predicate: str):
        try:
            facts = self._memory.knowledge.query(subject="user", predicate=predicate)
            return facts[-1] if facts else None
        except Exception:  # noqa: BLE001
            return None

    def _recall_all(self) -> dict[str, Any]:
        try:
            facts = self._memory.knowledge.query(subject="user")
        except Exception:  # noqa: BLE001
            facts = []
        if not facts:
            return {"kind": "reply", "text": "I don't have any personal facts about you stored yet."}
        lines = [f"{f.predicate}: {f.obj}" for f in facts]
        return {
            "kind": "reply",
            "text": "Here's what I remember about you:\n" + "\n".join(lines),
            "data": {"facts": [f.to_dict() for f in facts]},
        }

    def _search_memories(self, query: str) -> dict[str, Any]:
        try:
            if query:
                results = self._memory.hybrid_search(query, top_k=5)
                items = [r.content for r in results]
            else:
                items = [m.get("content", "") for m in self._memory.get_recent(10)]
        except Exception:  # noqa: BLE001
            items = []
        if not items:
            return {"kind": "reply", "text": "No memories found."}
        lines = [f"- {item}" for item in items]
        return {"kind": "reply", "text": "Memories:\n" + "\n".join(lines), "data": {"items": items}}

    def _forget(self, target: str) -> dict[str, Any]:
        target = (target or "").strip().strip(".!")
        if not target:
            return {"kind": "reply", "text": "What would you like me to forget?"}
        removed = 0
        if self._memory is not None:
            try:
                facts = self._memory.knowledge.query(subject="user")
                for fact in facts:
                    if target.lower() in fact.predicate.lower() or target.lower() in str(fact.obj).lower():
                        self._memory.knowledge.delete_fact(fact.id)
                        removed += 1
            except Exception:  # noqa: BLE001
                pass
            try:
                items = self._memory.storage.get("items", [])
                kept = [
                    item
                    for item in items
                    if target.lower() not in str(item.get("content", "")).lower()
                ]
                removed += len(items) - len(kept)
                self._memory.storage.set("items", kept)
            except Exception:  # noqa: BLE001
                pass
        if removed == 0:
            return {"kind": "reply", "text": f"I couldn't find anything about '{target}' to forget."}
        return {
            "kind": "reply",
            "text": f"Forgot {removed} memory item(s) about '{target}'.",
            "data": {"removed": removed},
        }

    # ------------------------------------------------------------------
    # Tools (including desktop and browser tools)
    # ------------------------------------------------------------------

    def _execute_tool(self, classification: IntentClassification) -> dict[str, Any]:
        name = classification.target or ""
        params = dict(classification.params)
        tool = self._tools.get(name)
        if tool is None:
            return {"kind": "reply", "text": f"The {name} is not available right now."}

        prompt = self._missing_param_prompt(name, params)
        if prompt:
            return {"kind": "reply", "text": prompt}

        # P30 Phase 5: high-risk desktop actions MUST stay approval-gated.
        risk_fn = getattr(tool, "risk_of", None)
        if callable(risk_fn) and self._approval is not None:
            action = str(params.get("action", ""))
            if risk_fn(action) == "high":
                return self._propose_desktop_approval(name, action, params)

        return self._run_tool(name, params)

    def _propose_desktop_approval(
        self, name: str, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Arm the approval gate for a high-risk desktop action."""
        brief = ", ".join(f"{k}={v}" for k, v in params.items() if k != "action")
        proposal = f"Approve the desktop {action}?"
        if brief:
            proposal += f"\nDetails: {brief}"
        return self._approval.propose(
            action_type="desktop_control",
            request=f"{name}: {action}" + (f" ({brief})" if brief else ""),
            proposal=proposal,
            executor=lambda: self._run_tool(name, params),
            data={
                "tool": name,
                "action": action,
                "risk": "high",
                "params": dict(params),
            },
        )

    @staticmethod
    def _missing_param_prompt(name: str, params: dict[str, Any]) -> str | None:
        if name == "python_tool" and not params.get("source"):
            return "What Python code would you like me to run? For example: run python print(1+1)"
        if name == "git_tool" and params.get("action") in (None, "clone") and not params.get("repo_url"):
            return "Which repository would you like me to clone? For example: clone repository https://github.com/user/repo"
        if name == "git_tool" and params.get("action") == "commit" and not params.get("message"):
            return "What should I use as the commit message? For example: commit changes -m 'my message'"
        if name == "rest_tool" and not params.get("url"):
            return "Which URL would you like me to call? For example: call REST endpoint https://api.example.com"
        if name == "shell_tool" and not params.get("command"):
            return "What shell command would you like me to run?"
        if name == "desktop_tool" and not params.get("action"):
            return "What would you like me to do? For example: open chrome or shutdown computer"
        return None

    def _run_tool(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"kind": "reply", "text": f"Tool {name!r} is not available."}

        start = time.monotonic()
        result = None
        attempts = 0
        while attempts < 2:
            attempts += 1
            try:
                result = tool.execute(params)
            except Exception as exc:  # noqa: BLE001
                result = type(
                    "ToolResult",
                    (),
                    {
                        "success": False,
                        "error_message": f"{type(exc).__name__}: {exc}",
                        "output": None,
                    },
                )()
            if result.success:
                break
            if attempts >= 2:
                break
        duration_ms = (time.monotonic() - start) * 1000

        record: dict[str, Any] = {
            "tool": name,
            "params": params,
            "success": bool(getattr(result, "success", False)),
            "duration_ms": round(duration_ms, 1),
            "attempts": attempts,
        }
        if self._tool_result_sink is not None:
            self._tool_result_sink(record)
        self._record_execution("tool", name, record["success"])

        if not result.success:
            message = getattr(result, "error_message", "") or "failed"
            return {
                "kind": "reply",
                "text": f"I couldn't run the {name}: {message}",
                "data": record,
            }

        output = getattr(result, "output", None)
        summary = format_tool_output(name, output)
        record["output"] = output
        return {
            "kind": "reply",
            "text": f"Done ({name}).\n{summary}",
            "data": record,
        }

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def _execute_agent(self, classification: IntentClassification) -> dict[str, Any]:
        name = classification.target or ""
        instance = self._lookup_instance(name)
        registration = self._find_agent(name)
        state_key = (registration.name if registration is not None else name).lower()
        state = self._agent_runtime.setdefault(state_key, _new_agent_state())

        if instance is None and registration is not None:
            return {
                "kind": "reply",
                "text": f"Agent '{registration.name}' is registered but has no runnable instance in this session.",
                "data": {"agent": registration.to_dict(), "route": "agent"},
            }

        if instance is None:
            return {
                "kind": "reply",
                "text": (
                    f"No agent named '{name}' is available. Try 'list agents' to see "
                    "registered agents, or 'list available tools' for direct actions."
                ),
                "data": {"route": "agent"},
            }

        # Session lifecycle gates: paused / stopped agents refuse to run.
        if state["status"] in (AGENT_STATE_PAUSED, AGENT_STATE_STOPPED):
            _append_agent_log(state, f"run refused while {state['status']}")
            return {
                "kind": "reply",
                "text": (
                    f"Agent '{name}' is {state['status']}. Say 'resume agent {name}' "
                    "to enable it again."
                ),
                "data": {
                    "agent": name,
                    "action": "skip",
                    "status": state["status"],
                    "route": "agent",
                },
            }

        state["status"] = AGENT_STATE_RUNNING
        state["runs"] += 1
        state["last_start"] = time.monotonic()
        _append_agent_log(state, f"run #{state['runs']} started")
        self._publish(
            "agent.status", name=name, status=AGENT_STATE_RUNNING, runs=state["runs"]
        )
        start = time.monotonic()
        try:
            result = instance.execute({"request": classification.params.get("request", "")})
        except Exception as exc:  # noqa: BLE001
            state["status"] = AGENT_STATE_FAILED
            state["last_error"] = f"{type(exc).__name__}: {exc}"
            state["last_end"] = time.monotonic()
            _append_agent_log(state, f"run #{state['runs']} failed: {state['last_error']}")
            self._publish(
                "agent.status", name=name, status=AGENT_STATE_FAILED,
                error=state["last_error"],
            )
            self._record_execution("agent", name, False)
            return {
                "kind": "reply",
                "text": f"Agent '{name}' failed: {state['last_error']}",
                "data": {
                    "agent": name,
                    "success": False,
                    "status": AGENT_STATE_FAILED,
                    "route": "agent",
                },
            }
        duration_ms = (time.monotonic() - start) * 1000
        state["status"] = AGENT_STATE_COMPLETED
        state["last_end"] = time.monotonic()
        state["last_message"] = result.get("message") or result.get("text") or str(result)
        text = state["last_message"]
        _append_agent_log(state, f"run #{state['runs']} completed in {round(duration_ms)} ms")
        self._publish(
            "agent.status", name=name, status=AGENT_STATE_COMPLETED, runs=state["runs"]
        )
        self._record_execution("agent", name, True)

        return {
            "kind": "reply",
            "text": text[:MAX_REPLY_CHARS],
            "data": {
                "agent": name,
                "success": True,
                "status": AGENT_STATE_COMPLETED,
                "runs": state["runs"],
                "duration_ms": round(duration_ms, 1),
                "output": result,
                "route": "agent",
            },
        }

    def _control_agent(self, classification: IntentClassification) -> dict[str, Any]:
        action = classification.target or ""
        name = (classification.params.get("name") or "").strip().lower()
        registration = self._find_agent(name)
        instance = self._lookup_instance(name)
        display = (registration.name if registration is not None else name) or name
        state_key = display.lower()
        state = self._agent_runtime.setdefault(state_key, _new_agent_state())

        if action == "delete":
            if instance is None and registration is None:
                return {
                    "kind": "reply",
                    "text": f"No agent named '{name}' is available.",
                    "data": {"agent": name, "route": "agent_ctrl"},
                }
            self._drop_instance(name)
            removed = False
            if self._agents is not None and registration is not None:
                try:
                    removed = bool(self._agents.unregister(registration.agent_id))
                except Exception:  # noqa: BLE001
                    removed = False
            self._agent_runtime.pop(state_key, None)
            _append_agent_log(state, "deleted from session")
            self._publish(
                "agent.deleted",
                name=display,
                agent_id=registration.agent_id if registration else "",
            )
            return {
                "kind": "reply",
                "text": (
                    f"Agent '{display}' deleted from this session"
                    + (" and unregistered." if removed else ".")
                ),
                "data": {
                    "agent": display,
                    "route": "agent_ctrl",
                    "action": "delete",
                    "unregistered": removed,
                },
            }

        if instance is None:
            return {
                "kind": "reply",
                "text": f"No agent named '{name}' is available.",
                "data": {"agent": name, "route": "agent_ctrl"},
            }

        if action == "pause":
            if state["status"] == AGENT_STATE_PAUSED:
                return {"kind": "reply", "text": f"Agent '{display}' is already paused."}
            state["status"] = AGENT_STATE_PAUSED
            _append_agent_log(state, "paused")
            self._publish(
                "agent.status", name=display, status=AGENT_STATE_PAUSED, action="pause"
            )
            cascaded = self._cascade_agent_control("pause", registration)
            suffix = f" (children also paused: {', '.join(cascaded)})" if cascaded else ""
            return {
                "kind": "reply",
                "text": (
                    f"Agent '{display}' paused{suffix}. Say 'resume agent {display}' to "
                    "enable it again."
                ),
                "data": {"agent": display, "status": "paused", "route": "agent_ctrl", "action": "pause", "cascaded": cascaded},
            }
        if action == "resume":
            if state["status"] not in (AGENT_STATE_PAUSED, AGENT_STATE_STOPPED, AGENT_STATE_FAILED):
                return {"kind": "reply", "text": f"Agent '{display}' is not paused (status: {state['status']})."}
            state["status"] = AGENT_STATE_READY
            _append_agent_log(state, "resumed")
            self._publish(
                "agent.status", name=display, status=AGENT_STATE_READY, action="resume"
            )
            cascaded = self._cascade_agent_control("resume", registration)
            suffix = f" (children also resumed: {', '.join(cascaded)})" if cascaded else ""
            return {
                "kind": "reply",
                "text": f"Agent '{display}' resumed and ready to run.{suffix}",
                "data": {"agent": display, "status": "ready", "route": "agent_ctrl", "action": "resume", "cascaded": cascaded},
            }
        if action == "stop":
            state["status"] = AGENT_STATE_STOPPED
            _append_agent_log(state, "stopped")
            self._publish(
                "agent.status", name=display, status=AGENT_STATE_STOPPED, action="stop"
            )
            cascaded = self._cascade_agent_control("stop", registration)
            suffix = f" (children also stopped: {', '.join(cascaded)})" if cascaded else ""
            return {
                "kind": "reply",
                "text": (
                    f"Agent '{display}' stopped{suffix}. Say 'resume agent {display}' to "
                    "enable it again."
                ),
                "data": {"agent": display, "status": "stopped", "route": "agent_ctrl", "action": "stop", "cascaded": cascaded},
            }
        if action == "status":
            lines = [f"Agent '{display}': {state['status']}", f"  runs: {state['runs']}"]
            if state["last_error"]:
                lines.append(f"  last error: {state['last_error']}")
            if state["last_message"]:
                lines.append(f"  last message: {state['last_message'][:200]}")
            return {
                "kind": "reply",
                "text": "\n".join(lines),
                "data": {
                    "agent": display,
                    "status": state["status"],
                    "runs": state["runs"],
                    "last_error": state["last_error"],
                    "route": "agent_ctrl",
                },
            }
        if action == "logs":
            logs = state["logs"][-20:]
            if not logs:
                return {
                    "kind": "reply",
                    "text": f"Agent '{display}' has no logged activity yet.",
                    "data": {"agent": display, "logs": [], "route": "agent_ctrl"},
                }
            return {
                "kind": "reply",
                "text": f"Logs for agent '{display}':\n" + "\n".join(logs),
                "data": {"agent": display, "logs": logs[-10:], "route": "agent_ctrl"},
            }
        return {"kind": "reply", "text": "I didn't understand that."}

    def agent_status_table(self) -> str | None:
        """Live session status for every runnable agent instance."""
        if not self._agent_instances:
            return None
        lines = ["Agents (live session status):"]
        seen: set[str] = set()
        for key, instance in self._agent_instances.items():
            name = getattr(instance, "name", None) or key
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            status = self._agent_runtime.get(name.lower(), _new_agent_state())["status"]
            agent_type = getattr(getattr(instance, "metadata", None), "agent_type", "")
            suffix = f" ({agent_type})" if agent_type else ""
            lines.append(f"  {name}: {status}{suffix}")
        return "\n".join(lines)

    def _find_agent(self, name: str):
        if self._agents is None:
            return None
        lowered = name.lower()
        normalized = lowered.replace(" ", "").replace("_", "")
        try:
            for registration in self._agents.list():
                reg_name = registration.name.lower()
                reg_normalized = reg_name.replace(" ", "").replace("_", "")
                if (
                    reg_name == lowered
                    or registration.agent_id.lower() == lowered
                    or (normalized and reg_normalized == normalized)
                    or (normalized and reg_normalized.startswith(normalized))
                ):
                    return registration
        except Exception:  # noqa: BLE001
            return None
        return None

    def _lookup_instance(self, name: str):
        """Case-insensitive lookup of a runnable session instance."""
        if not name:
            return None
        lowered = name.lower()
        instance = self._agent_instances.get(name) or self._agent_instances.get(lowered)
        if instance is not None:
            return instance
        for key, inst in self._agent_instances.items():
            if key.lower() == lowered:
                return inst
        return None

    def _cascade_agent_control(self, action: str, registration: Any) -> list[str]:
        """Propagate pause/resume/stop to child agents (P29 hierarchy).

        Only children with live session state are affected; resume only
        touches children that are actually paused.  Returns the names of
        affected children.
        """
        if registration is None or self._agents is None:
            return []
        try:
            children = self._agents.children_of(registration.agent_id)
        except Exception:  # noqa: BLE001
            return []
        target = {
            "pause": AGENT_STATE_PAUSED,
            "stop": AGENT_STATE_STOPPED,
            "resume": AGENT_STATE_READY,
        }.get(action)
        if target is None:
            return []
        affected: list[str] = []
        for child in children:
            child_state = self._agent_runtime.get(child.name.lower())
            if child_state is None:
                if self._lookup_instance(child.name) is None:
                    continue
                # Runnable child with no session state yet: seed it so
                # the cascade is tracked from the very first control.
                child_state = self._agent_runtime.setdefault(
                    child.name.lower(), _new_agent_state()
                )
            if action == "resume" and child_state["status"] != AGENT_STATE_PAUSED:
                continue
            child_state["status"] = target
            _append_agent_log(
                child_state,
                f"{target} (cascaded from parent '{registration.name}')",
            )
            self._publish(
                "agent.status",
                name=child.name,
                status=target,
                action=action,
                cascaded=True,
            )
            affected.append(child.name)
        return affected

    def _drop_instance(self, name: str) -> None:
        """Remove every instance key matching *name* case-insensitively."""
        lowered = name.lower()
        for key in [k for k in self._agent_instances if k.lower() == lowered]:
            self._agent_instances.pop(key, None)

    # ------------------------------------------------------------------
    # Missions (P28 — NL surface over app.mission)
    # ------------------------------------------------------------------

    def _mission_manager(self):
        """Shared process-wide mission manager (tests may inject one)."""
        if self._mission_manager_override is not None:
            manager = self._mission_manager_override
        else:
            from app.mission.manager import get_mission_manager

            manager = get_mission_manager()
        # Wire the kernel event bus into the shared manager so mission
        # lifecycle events (task_done, completed, ...) reach the bus.
        if self._bus is not None:
            try:
                manager._services.setdefault("event_bus", self._bus)
            except Exception:  # noqa: BLE001
                pass
        return manager

    def _execute_mission(self, classification: IntentClassification) -> dict[str, Any]:
        action = classification.target or "status"
        if action == "start":
            return self._propose_mission(classification.params.get("goal", ""))
        return self._control_mission(action, classification.params.get("ref", ""))

    def _propose_mission(self, goal: str) -> dict[str, Any]:
        """Plan a mission (read-only) and arm the approval gate."""
        goal = (goal or "").strip()
        if not goal:
            return {"kind": "reply", "text": "A mission needs a goal."}
        if self._approval is None:
            return {
                "kind": "reply",
                "text": "The mission engine is not available right now.",
            }
        manager = self._mission_manager()
        try:
            mission = manager.create(goal, ai=self._ai)
            manager.await_approval(mission)
            from app.mission.planner import render_mission_proposal

            proposal_text = render_mission_proposal(mission)
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": f"Mission planning failed: {type(exc).__name__}: {exc}",
                "data": {"error": str(exc)},
            }
        self._publish(
            "mission.proposed", mission_id=mission.id, title=mission.title
        )
        return self._approval.propose(
            action_type="mission",
            request=goal,
            proposal=proposal_text,
            data={"mission_id": mission.id},
            executor=lambda: self._approve_mission(mission.id),
        )

    def _approve_mission(self, mission_id: str) -> dict[str, Any]:
        """Approve the mission; execution continues in the background."""
        manager = self._mission_manager()
        try:
            result = manager.approve(mission_id)
        except KeyError:
            return {
                "kind": "reply",
                "text": "That mission no longer exists.",
                "data": {"mission_id": mission_id},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": f"Mission launch failed: {type(exc).__name__}: {exc}",
                "data": {"mission_id": mission_id, "error": str(exc)},
            }
        mission = manager.get(mission_id)
        title = mission.title if mission is not None else mission_id
        text = (
            f"Mission '{title}' approved and running in the background "
            f"(id {mission_id[:8]}). Say 'mission status' for progress, "
            f"'pause mission' or 'cancel mission' to control it."
        )
        self._record_execution("mission", f"mission:{title}", True)
        self._publish(
            "mission.approved", mission_id=mission_id, title=title, status="running"
        )
        return {
            "kind": "mission",
            "text": text,
            "data": {
                "mission_id": mission_id,
                "status": result.get("status", "running"),
                "route": "mission",
            },
        }

    def _control_mission(self, action: str, ref: str) -> dict[str, Any]:
        manager = self._mission_manager()
        mission = self._resolve_mission(ref)
        if mission is None:
            if ref:
                return {
                    "kind": "reply",
                    "text": f"No mission matching '{ref}' was found.",
                    "data": {"route": "mission"},
                }
            return {
                "kind": "reply",
                "text": "There is no active mission right now.",
                "data": {"route": "mission"},
            }
        if action == "status":
            return {
                "kind": "reply",
                "text": self._mission_status_text(mission),
                "data": {"mission_id": mission.id, "route": "mission"},
            }
        try:
            if action == "pause":
                manager.pause(mission.id)
            elif action == "resume":
                manager.resume(mission.id)
            elif action == "cancel":
                manager.cancel(mission.id)
            else:
                return {"kind": "reply", "text": "I didn't understand that."}
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": f"Mission {action} failed: {type(exc).__name__}: {exc}",
                "data": {"mission_id": mission.id, "error": str(exc)},
            }
        refreshed = manager.get(mission.id) or mission
        status = getattr(refreshed.status, "value", str(refreshed.status))
        verb = {"pause": "paused", "resume": "resumed", "cancel": "cancelled"}[action]
        self._record_execution("mission", f"mission:{mission.title}:{action}", True)
        self._publish(
            "mission.status",
            mission_id=mission.id,
            title=mission.title,
            action=action,
            status=status,
        )
        return {
            "kind": "reply",
            "text": (
                f"Mission '{mission.title}' {verb} "
                f"(id {mission.id[:8]}, status {status}, "
                f"progress {getattr(refreshed, 'progress', 0)}%)."
            ),
            "data": {
                "mission_id": mission.id,
                "action": action,
                "status": status,
                "route": "mission",
            },
        }

    def _resolve_mission(self, ref: str):
        """Resolve a mission by id/title prefix; default to the active one."""
        manager = self._mission_manager()
        ref = (ref or "").strip()
        if not ref:
            try:
                return manager.active()
            except Exception:  # noqa: BLE001
                return None
        lowered = ref.lower()
        try:
            for mission in manager.list():
                title = (mission.title or "").lower()
                if (
                    mission.id == ref
                    or mission.id.startswith(ref)
                    or title == lowered
                    or title.startswith(lowered)
                ):
                    return mission
        except Exception:  # noqa: BLE001
            return None
        return None

    def _mission_status_text(self, mission: Any) -> str:
        status = getattr(mission.status, "value", str(mission.status))
        lines = [
            f"Mission '{mission.title}' (id {mission.id[:8]}):",
            f"  status: {status}",
            f"  progress: {getattr(mission, 'progress', 0)}%",
            f"  goal: {mission.goal}",
        ]
        try:
            running = [
                task.title for task in mission.tasks
                if getattr(task.status, "value", "") == "running"
            ]
            if running:
                lines.append("  running tasks: " + ", ".join(running[:5]))
            done = sum(
                1 for task in mission.tasks
                if getattr(task.status, "value", "") == "completed"
            )
            lines.append(f"  tasks: {done}/{len(mission.tasks)} completed")
        except Exception:  # noqa: BLE001
            pass
        result = getattr(mission, "result", None) or {}
        if result.get("error"):
            lines.append(f"  last error: {result['error']}")
        return "\n".join(lines)

    def mission_status_table(self) -> str:
        """Render the mission list for the runtime's missions command."""
        manager = self._mission_manager()
        try:
            missions = manager.list()
        except Exception:  # noqa: BLE001
            missions = []
        if not missions:
            return "No missions have been created yet."
        lines = ["Missions:"]
        for mission in missions[-10:]:
            status = getattr(mission.status, "value", str(mission.status))
            lines.append(
                f"  {mission.title} (id {mission.id[:8]}): "
                f"{status}, {getattr(mission, 'progress', 0)}%"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Knowledge graph
    # ------------------------------------------------------------------

    def _execute_knowledge(self, classification: IntentClassification) -> dict[str, Any]:
        if self._graph is None:
            return {"kind": "reply", "text": "The knowledge graph is not available right now."}

        action = classification.target or "summary"
        try:
            if action == "entities":
                return self._knowledge_entities()
            if action == "capabilities":
                return self._knowledge_capabilities()
            if action == "relationships":
                return self._knowledge_relationships()
            return self._knowledge_summary()
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": f"I couldn't query the knowledge graph: {exc}",
            }

    def _knowledge_entities(self) -> dict[str, Any]:
        lines: list[str] = []
        for entity_type in (
            "concept", "tool", "agent", "capability", "task",
            "skill", "plugin", "project", "file", "memory", "workflow",
        ):
            try:
                entities = self._graph.get_entities_by_type(entity_type)
            except Exception:  # noqa: BLE001
                entities = []
            if entities:
                names = ", ".join(e.name for e in entities[:20])
                lines.append(f"{entity_type}: {names}")
        if not lines:
            return {"kind": "reply", "text": "No entities recorded in the knowledge graph yet."}
        return {"kind": "reply", "text": "Knowledge graph entities:\n" + "\n".join(lines)}

    def _knowledge_capabilities(self) -> dict[str, Any]:
        try:
            capabilities = self._graph.get_entities_by_type("capability")
        except Exception:  # noqa: BLE001
            capabilities = []
        if not capabilities:
            return {"kind": "reply", "text": "No capabilities recorded in the knowledge graph yet."}
        lines = [f"- {c.name}" for c in capabilities]
        return {"kind": "reply", "text": "Capabilities:\n" + "\n".join(lines)}

    def _knowledge_relationships(self) -> dict[str, Any]:
        lines: list[str] = []
        seen = 0
        for entity_type in (
            "concept", "tool", "agent", "capability", "task",
            "skill", "plugin", "project", "file", "memory", "workflow",
        ):
            if seen >= 60:
                break
            try:
                entities = self._graph.get_entities_by_type(entity_type)
            except Exception:  # noqa: BLE001
                entities = []
            for entity in entities:
                if seen >= 60:
                    break
                try:
                    relations = self._graph.get_outgoing_relationships(entity.id)
                except Exception:  # noqa: BLE001
                    relations = []
                for rel in relations:
                    target = self._graph.get_entity(rel["target_id"])
                    if target is None:
                        continue
                    lines.append(f"{entity.name} --{rel['type']}--> {target.name}")
                    seen += 1
        if not lines:
            return {"kind": "reply", "text": "No relationships recorded in the knowledge graph yet."}
        return {"kind": "reply", "text": "Knowledge graph relationships:\n" + "\n".join(lines)}

    def _knowledge_summary(self) -> dict[str, Any]:
        try:
            entity_count = self._graph.entity_count()
            relationship_count = self._graph.relationship_count()
        except Exception:  # noqa: BLE001
            entity_count = 0
            relationship_count = 0
        return {
            "kind": "reply",
            "text": (
                f"Knowledge graph: {entity_count} entities and "
                f"{relationship_count} relationships."
            ),
            "data": {"entities": entity_count, "relationships": relationship_count},
        }

    # ------------------------------------------------------------------
    # Planning / evolution / agent creation (approval-gated flows)
    # ------------------------------------------------------------------

    def _propose_plan(self, request: str) -> dict[str, Any]:
        """Generate a read-only implementation plan and arm approval."""
        if self._ai is None or self._approval is None:
            return {"kind": "build", "text": "", "request": request}
        proposal, meta = self._build_plan_proposal(request)
        if proposal is None:
            return {"kind": "build", "text": "", "request": request}
        return self._approval.propose(
            action_type="plan",
            request=request,
            proposal=proposal,
            data=meta,
            executor=lambda: self._run_plan_pipeline(request),
        )

    def _build_plan_proposal(self, request: str) -> tuple[str | None, dict[str, Any]]:
        try:
            result = self._ai.plan(request)
        except Exception:  # noqa: BLE001
            return None, {}
        plan = getattr(result, "plan", None)
        if plan is None:
            return None, {}
        text = _render_plan_proposal(plan)
        meta = {
            "plan": {
                "title": plan.title,
                "objective": plan.objective,
                "steps": [
                    {
                        "id": step.id,
                        "title": step.title,
                        "action_type": getattr(
                            step.action_type, "value", str(step.action_type)
                        ),
                        "description": step.description,
                        "expected_output": step.expected_output,
                        "depends_on": list(step.depends_on),
                    }
                    for step in (plan.steps or ())
                ],
            },
            "valid": bool(getattr(result, "valid", False)),
            "validation_errors": list(
                getattr(result, "validation_errors", []) or []
            ),
        }
        return text, meta

    def _run_plan_pipeline(self, request: str) -> dict[str, Any]:
        """Execute the approved plan through the build orchestrator."""
        if self._orchestrator is None:
            return {
                "kind": "reply",
                "text": "The build orchestrator is not available right now.",
            }
        try:
            build_result = self._orchestrator.build(request)
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": f"Execution failed: {type(exc).__name__}: {exc}",
                "data": {"error": str(exc)},
            }
        return _build_result_summary(build_result)

    def _propose_evolve(self, objective: str) -> dict[str, Any]:
        """Analyze the project, propose self-improvements, arm approval."""
        if self._ai is None or self._approval is None:
            return {
                "kind": "reply",
                "text": "The evolution engine is not available right now.",
            }
        manager = self._evolution_manager()
        try:
            proposal = manager.propose(objective)
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": (
                    f"Evolution analysis failed: {type(exc).__name__}: {exc}"
                ),
                "data": {"error": str(exc)},
            }
        # P21-27: the executed pipeline must work on a target that the
        # approved proposal actually names (when it names one at all),
        # instead of always executing the canned default task.
        target = _evolve_target_from_proposal(proposal)
        return self._approval.propose(
            action_type="evolve",
            request=objective,
            proposal=proposal.get(
                "proposal_text", "Evolution proposal."
            ),
            data={
                "objective": objective,
                "analysis": proposal.get("analysis", {}),
                "plan": proposal.get("plan", ""),
                "target": target,
            },
            executor=lambda: self._run_evolution_pipeline(objective, target),
        )

    def _run_evolution_pipeline(
        self,
        objective: str,
        target: str | None = None,
    ) -> dict[str, Any]:
        """Execute the approved evolution pipeline (install gated by policy)."""
        manager = self._evolution_manager()
        try:
            if target is None:
                report = manager.execute(objective=objective)
            else:
                report = manager.execute(
                    objective=objective,
                    task=f"Apply the approved improvement to {target}.",
                    target=target,
                )
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": f"Evolution failed: {type(exc).__name__}: {exc}",
                "data": {"error": str(exc)},
            }
        return {
            "kind": "evolve",
            "text": _evolution_result_text(report),
            "data": report,
        }

    def _evolution_manager(self):
        from app.evolution.manager import EvolutionManager

        registry = {
            "ai_manager": self._ai,
            "ai_router": getattr(self._ai, "router", None),
        }
        return EvolutionManager(registry=registry)

    def _objective_engine(self):
        """P32 autonomous workflow engine bound to this router's subsystems."""
        if self._workflow_engine_override is not None:
            return self._workflow_engine_override
        if hasattr(self, "_cached_objective_engine"):
            return self._cached_objective_engine
        from app.autonomy.workflow.engine import AutonomousWorkflowEngine

        self._cached_objective_engine = AutonomousWorkflowEngine(
            approval=self._approval,
            event_bus=self._bus,
            ai=self._ai,
            memory=self._memory,
            agents=self._agents,
            agent_instances=self._agent_instances,
            mission_manager=self._mission_manager() if self._mission_manager_override else None,
            goal_manager=self._goal_manager,
            timeline=self._timeline,
            registry_services={
                "ai_manager": self._ai,
                "ai_router": getattr(self._ai, "router", None),
            },
        )
        return self._cached_objective_engine

    def _objective_orchestrator(self):
        """P33 capability orchestrator bound to this router's subsystems.

        Wraps the router-bound P32 engine: same approval gate, same
        staged pipeline, with capability acquisition bookkeeping on top.
        """
        if getattr(self, "_orchestrator_override", None) is not None:
            return self._orchestrator_override
        from app.autonomy.acquisition.orchestrator import CapabilityOrchestrator

        return CapabilityOrchestrator(
            engine=self._objective_engine(),
            event_bus=self._bus,
            ai=self._ai,
            memory=self._memory,
            approval=self._approval,
        )

    def _execute_objective(self, request: str) -> dict[str, Any]:
        """Plan an objective (read-only) and arm the workflow approval."""
        request = (request or "").strip()
        if not request:
            return {"kind": "reply", "text": "An objective needs a goal."}
        if self._approval is None:
            return {
                "kind": "reply",
                "text": "The autonomous workflow engine is not available right now.",
            }
        engine = self._objective_engine()
        try:
            return self._objective_orchestrator().submit(request)
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": f"Objective planning failed: {type(exc).__name__}: {exc}",
                "data": {"error": str(exc)},
            }

    def _render_agent_spec_text(
        self, spec: dict[str, Any], request: str
    ) -> str:
        """Format an agent spec as human-readable proposal text."""
        capabilities, unknown = self._resolve_spec_capabilities(spec)
        name = spec.get("name") or (
            "_".join([w for w in request.split() if w.isalnum()][:3])
            or "assistant_agent"
        )
        lines = [
            "AGENT PROPOSAL",
            "",
            f"Name: {name}",
            f"Type: {spec.get('agent_type', 'domain')}",
        ]
        if spec.get("objective"):
            lines.append(f"Objective: {spec['objective']}")
        if spec.get("description"):
            lines.append(f"Description: {spec['description']}")
        if spec.get("responsibilities"):
            lines.append("Responsibilities:")
            lines.extend(f"  - {item}" for item in spec["responsibilities"])
        if capabilities:
            lines.append("Capabilities: " + ", ".join(c.name for c in capabilities))
        if unknown:
            lines.append("Unknown capabilities (ignored): " + ", ".join(unknown))
        tools = self._spec_tools(spec, capabilities)
        if tools:
            lines.append(f"Tools: {', '.join(tools)}")
        if spec.get("approval_requirements"):
            lines.append(
                "Approval required for: "
                + ", ".join(str(a) for a in spec["approval_requirements"])
            )
        if spec.get("memory_scope") or spec.get("memory"):
            lines.append(
                f"Memory: {spec.get('memory_scope') or spec['memory']}"
            )
        if spec.get("parent"):
            lines.append(f"Parent agent: {spec['parent']}")
        if spec.get("events"):
            lines.append(f"Events: {', '.join(spec['events'])}")
        if spec.get("communication"):
            lines.append(f"Communication: {spec['communication']}")
        return "\n".join(lines)

    def _propose_agent(self, request: str) -> dict[str, Any]:
        """Design an agent (name / responsibilities / tools / memory ...)."""
        if self._ai is None or self._approval is None or self._agents is None:
            return {
                "kind": "reply",
                "text": "Agent creation is not available right now.",
            }
        spec_text, spec = self._build_agent_spec(request)
        if spec_text is None:
            return {
                "kind": "reply",
                "text": "I couldn't design that agent right now.",
            }
        _capabilities, unknown = self._resolve_spec_capabilities(spec)
        if unknown:
            # P32: capability-gap chain. The agent needs capabilities
            # JARVIS does not have yet; arm a development gate first.
            try:
                engine = self._objective_engine()
                gap_reply = engine.ensure_capabilities(
                    unknown, request, after=lambda ok, detail: (
                        self._propose_agent_after_upgrade(request, spec, ok, detail)
                    )
                )
            except Exception as exc:  # noqa: BLE001
                gap_reply = {
                    "kind": "reply",
                    "text": (
                        "Agent capability development could not be prepared: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    "data": {"error": str(exc)},
                }
            if gap_reply.get("kind") == "approval_required":
                return self._approval.propose(
                    action_type="agent_with_capability_upgrade",
                    request=request,
                    proposal=(
                        spec_text
                        + "\n\nNote: the requested agent needs capabilities "
                        "JARVIS does not have yet: "
                        + ", ".join(unknown)
                        + ". After approving this, you will be asked to "
                        "approve the capability development itself, and then "
                        "the agent creation."
                    ),
                    data={"spec": spec, "gaps": unknown},
                    executor=lambda: self._approve_agent_with_upgrade(
                        request, spec, unknown
                    ),
                )
        return self._approval.propose(
            action_type="agent_create",
            request=request,
            proposal=spec_text,
            data={"spec": spec},
            executor=lambda: self._run_agent_pipeline(request, spec),
        )

    def _approve_agent_with_upgrade(
        self,
        request: str,
        spec: dict[str, Any],
        unknown: list[str],
    ) -> dict[str, Any]:
        """Approve capability development; chain the agent gate after it."""
        engine = self._objective_engine()
        return engine.ensure_capabilities(
            unknown,
            request,
            after=lambda ok, detail: self._propose_agent_after_upgrade(
                request, spec, ok, detail
            ),
        )

    def _propose_agent_after_upgrade(
        self,
        request: str,
        spec: dict[str, Any],
        upgrade_ok: bool,
        detail: str,
    ) -> dict[str, Any]:
        """Arm the agent-creation gate once capabilities are installed."""
        capabilities, still_unknown = self._resolve_spec_capabilities(spec)
        if not upgrade_ok or still_unknown:
            return {
                "kind": "reply",
                "text": (
                    "Capability development incomplete: " + detail
                    + (
                        "; still missing: " + ", ".join(still_unknown)
                        if still_unknown else ""
                    )
                ),
                "data": {"remaining": still_unknown},
            }
        cap_text = ", ".join(c.name for c in capabilities)
        text = self._render_agent_spec_text(spec, request)
        return self._approval.propose(
            action_type="agent_create",
            request=request,
            proposal=text,
            data={"spec": spec, "capabilities": cap_text},
            executor=lambda: self._run_agent_pipeline(request, spec),
        )

    def _build_agent_spec(self, request: str) -> tuple[str | None, dict[str, Any]]:
        try:
            from app.agents.capabilities import get_capability_registry

            known = ", ".join(get_capability_registry().names())
        except Exception:  # noqa: BLE001
            known = "browser, filesystem, shell, desktop, memory, knowledge"
        prompt = (
            "Design a JARVIS OS agent for this request: " + request + "\n\n"
            "Return ONLY a JSON object with these keys: name, agent_type "
            "(one of system, tool, development, domain, composite), "
            "objective (one sentence), description, responsibilities (list "
            "of strings), capabilities (list chosen ONLY from: " + known + "), "
            "tools (list of strings), permissions (list of strings), "
            "approval_requirements (list of sensitive actions needing user "
            "approval), memory_scope (string), events (list of strings), "
            "communication (string)."
        )
        try:
            answer = self._ai.ask(None, prompt)
        except Exception:  # noqa: BLE001
            return None, {}
        text = str(answer)
        data = _extract_json(text)
        spec = data if isinstance(data, dict) and data else {}
        _type_match = _AGENT_TYPE_PATTERN.search(request)
        if _type_match:
            spec["agent_type"] = _type_match.group(1).lower()
        if not spec:
            return (
                "AGENT PROPOSAL\n\n"
                f"Request: {request}\n\n{text[:2000]}",
                {},
            )
        name = spec.get("name") or (
            "_".join([w for w in request.split() if w.isalnum()][:3])
            or "assistant_agent"
        )
        lines = [
            "AGENT PROPOSAL",
            "",
            f"Name: {name}",
            f"Type: {spec.get('agent_type', 'domain')}",
        ]
        if spec.get("objective"):
            lines.append(f"Objective: {spec['objective']}")
        if spec.get("description"):
            lines.append(f"Description: {spec['description']}")
        if spec.get("responsibilities"):
            lines.append("Responsibilities:")
            for item in spec["responsibilities"]:
                lines.append(f"  - {item}")
        capabilities, unknown = self._resolve_spec_capabilities(spec)
        if capabilities:
            lines.append("Capabilities: " + ", ".join(c.name for c in capabilities))
        if unknown:
            lines.append("Unknown capabilities (ignored): " + ", ".join(unknown))
        tools = self._spec_tools(spec, capabilities)
        if tools:
            lines.append(f"Tools: {', '.join(tools)}")
        if spec.get("approval_requirements"):
            lines.append(
                "Approval required for: "
                + ", ".join(str(a) for a in spec["approval_requirements"])
            )
        if spec.get("memory_scope") or spec.get("memory"):
            lines.append(f"Memory: {spec.get('memory_scope') or spec['memory']}")
        if spec.get("parent"):
            lines.append(f"Parent agent: {spec['parent']}")
        if spec.get("events"):
            lines.append(f"Events: {', '.join(spec['events'])}")
        if spec.get("communication"):
            lines.append(f"Communication: {spec['communication']}")
        return "\n".join(lines), spec

    @staticmethod
    def _resolve_spec_capabilities(spec: dict[str, Any]):
        """Validate spec capabilities against the capability registry."""
        from app.agents.capabilities import get_capability_registry

        names: list[str] = []
        for item in spec.get("capabilities") or []:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
        return get_capability_registry().resolve(names)

    @staticmethod
    def _spec_tools(spec: dict[str, Any], capabilities: list[Any]) -> list[str]:
        """Union of spec-declared tools and capability-mapped tools."""
        tools: list[str] = []
        for tool in spec.get("tools") or []:
            if tool not in tools:
                tools.append(str(tool))
        for capability in capabilities:
            for tool in getattr(capability, "tools", []) or []:
                if tool not in tools:
                    tools.append(tool)
        return tools

    def _run_agent_pipeline(
        self,
        request: str,
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        """Create and register the approved agent."""
        from app.agents.factory import AgentFactory

        name = (spec.get("name") or "").strip()
        if not name:
            words = [w for w in request.split() if w.isalnum()][:3]
            name = "_".join(words) or "assistant_agent"
        capabilities, _unknown = self._resolve_spec_capabilities(spec)
        parent_registration = None
        parent_name = (spec.get("parent") or "").strip()
        if parent_name:
            parent_registration = self._find_agent(parent_name)
        try:
            agent = AgentFactory.create(
                agent_type=spec.get("agent_type", "domain"),
                name=name,
                description=spec.get("description", ""),
                capabilities=[c.to_dict() for c in capabilities] or spec.get("capabilities"),
                dependencies=spec.get("dependencies"),
                parent_agent_id=(
                    parent_registration.agent_id if parent_registration else ""
                ),
            )
            # Wire execution context so the Desktop-created DomainAgent
            # actually executes its objective instead of returning the
            # legacy stub dict.  Mirrors the handoff in AgentBuilder.
            if self._ai is not None:
                try:
                    from app.agents.capabilities import get_capability_registry

                    agent._ai = self._ai
                    agent._objective = spec.get("objective", "")
                    agent._capabilities_registry = get_capability_registry()
                    agent._project_root = os.getcwd()
                except Exception:  # noqa: BLE001
                    pass
            agent.status = AgentStatus.ACTIVE
            registration = self._agents.register(agent)
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": "reply",
                "text": f"Agent creation failed: {type(exc).__name__}: {exc}",
                "data": {"error": str(exc)},
            }
        # Link the delegation hierarchy + persist the dynamic spec data.
        if parent_registration is not None:
            try:
                self._agents.set_parent(registration.agent_id, parent_registration.agent_id)
                registration = self._agents.get(registration.agent_id) or registration
            except Exception:  # noqa: BLE001
                pass
        try:
            self._agents.update_properties(
                registration.agent_id,
                objective=str(spec.get("objective", ""))[:500],
                permissions=str(spec.get("permissions", ""))[:500],
                memory_scope=str(spec.get("memory_scope") or spec.get("memory", ""))[:200],
            )
        except Exception:  # noqa: BLE001
            pass
        self._agent_instances[registration.agent_id] = agent
        self._agent_instances[registration.name] = agent
        self._agent_runtime.setdefault(
            registration.name.lower(),
            _new_agent_state(
                f"Agent created (type '{agent.agent_type}'), status {agent.status.value}"
            ),
        )
        self._record_execution("agent", registration.name, True)
        parent_id = getattr(registration, "parent_agent_id", "") or ""
        self._publish(
            "agent.created",
            agent_id=registration.agent_id,
            name=registration.name,
            agent_type=getattr(registration, "agent_type", ""),
            parent=parent_id,
            capabilities=[c.name for c in capabilities],
        )
        text = (
            f"Agent '{registration.name}' created and registered "
            f"({registration.agent_id})."
        )
        if parent_registration is not None:
            text += f" Parent: '{parent_registration.name}'."
        if capabilities:
            text += " Capabilities: " + ", ".join(c.name for c in capabilities) + "."
        return {
            "kind": "agent",
            "text": text,
            "data": {
                "agent": registration.to_dict(),
                "capabilities": [c.name for c in capabilities],
                "parent": parent_id,
                "route": "agent_create",
            },
        }

    # ------------------------------------------------------------------
    # Time
    # ------------------------------------------------------------------

    def _execute_time(self) -> dict[str, Any]:
        now = _datetime.datetime.now()
        return {
            "kind": "reply",
            "text": now.strftime("It's %I:%M %p on %A, %B %d, %Y."),
            "data": {"datetime": now.isoformat()},
        }

    # ------------------------------------------------------------------
    # Knowledge graph execution records
    # ------------------------------------------------------------------

    def _record_execution(self, kind: str, name: str, success: bool) -> None:
        """Record every tool/agent/build execution in the knowledge graph."""
        self._publish(
            "task.execution",
            kind=kind,
            name=name,
            status="ok" if success else "failed",
        )
        if self._graph is None:
            return
        try:
            self._graph.create_entity(
                type="task",
                name=f"{kind}:{name}",
                properties={
                    "status": "ok" if success else "failed",
                    "kind": kind,
                    "timestamp": _datetime.datetime.now().isoformat(timespec="seconds"),
                },
            )
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Approval-gated flow helpers
# ---------------------------------------------------------------------------

_EVOLVE_TARGET_RE = re.compile(r"app/[A-Za-z0-9_./]+\.py")


def _evolve_target_from_proposal(proposal: dict[str, Any]) -> str | None:
    """Pick a real project file that the proposal explicitly names.

    The AI plan may suggest improving a specific module; when it names
    an existing file under ``app/`` the approved pipeline targets that
    file instead of the engine's canned default task.  Returns ``None``
    (fall back to the default task) when nothing safe is named.
    """
    for text in (proposal.get("plan", ""), proposal.get("proposal_text", "")):
        if not isinstance(text, str) or not text:
            continue
        for candidate in _EVOLVE_TARGET_RE.findall(text):
            cleaned = candidate.strip().strip("`'\"")
            if cleaned.endswith(".py") and os.path.isfile(cleaned):
                return cleaned
    return None


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from AI output."""
    import json as _json

    text = text.strip()
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return _json.loads(match.group(1))
        except _json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return _json.loads(match.group(0))
        except _json.JSONDecodeError:
            pass
    return {}


def _render_plan_proposal(plan) -> str:
    """Render a structured plan as an implementation-plan proposal."""
    lines = ["IMPLEMENTATION PLAN", ""]
    title = getattr(plan, "title", "")
    objective = getattr(plan, "objective", "")
    if title:
        lines.append(f"Title: {title}")
    lines.append(f"Objective: {objective}")
    lines.append("")
    lines.append("Architecture / steps:")
    for i, step in enumerate(getattr(plan, "steps", []) or [], 1):
        action = getattr(step.action_type, "value", str(step.action_type))
        lines.append(f"  {i}. [{step.id}] {step.title} ({action})")
        if getattr(step, "description", ""):
            lines.append(f"     {step.description}")
        if getattr(step, "expected_output", ""):
            lines.append(f"     Expected output: {step.expected_output}")
        if getattr(step, "depends_on", None):
            lines.append(f"     Depends on: {', '.join(step.depends_on)}")

    files: list[str] = []
    risks: list[str] = []
    test_steps: list[str] = []
    for step in getattr(plan, "steps", []) or []:
        meta = step.metadata or {}
        if meta.get("files"):
            files.extend(str(item) for item in meta["files"])
        if meta.get("risks"):
            risks.extend(str(item) for item in meta["risks"])
        output = (step.expected_output or "").lower()
        if "test" in output or "test" in (step.title or "").lower():
            test_steps.append(f"  {step.title}")

    if files:
        lines.append("")
        lines.append("Files to modify/create:")
        for item in files:
            lines.append(f"  - {item}")

    lines.append("")
    lines.append(
        "Dependencies: steps follow the order above; any step listing "
        "'Depends on' runs after its prerequisites."
    )
    if risks:
        lines.append("")
        lines.append("Risks:")
        for item in risks:
            lines.append(f"  - {item}")
    if test_steps:
        lines.append("")
        lines.append("Test strategy:")
        lines.extend(test_steps)
    return "\n".join(lines)


def _build_result_summary(result) -> dict[str, Any]:
    """Summarize a BuildOrchestrator result into a reply dict."""
    status = getattr(result, "status", None)
    status_value = getattr(status, "value", None) or str(status or "")
    data = result.to_dict() if hasattr(result, "to_dict") else {}
    if status_value == "completed":
        failed = [
            key
            for key, stage in (data.get("stages") or {}).items()
            if stage.get("status") == "failed"
        ]
        if not failed:
            return {
                "kind": "build",
                "text": "Build completed.\n"
                + str(getattr(result, "summary", "") or ""),
                "data": data,
            }
    return {
        "kind": "build",
        "text": f"Build failed: {getattr(result, 'error', '') or 'unknown error'}",
        "data": data,
    }


def _evolution_result_text(report: dict[str, Any]) -> str:
    """Render an evolution pipeline report as text."""
    lines = ["Evolution result", ""]
    if report.get("success"):
        lines.append("The improvement was applied after your approval.")
    else:
        lines.append("The improvement was blocked.")
    if report.get("summary"):
        lines.append(report["summary"])
    lines.append("")
    lines.append("Stages:")
    for name, outcome in (report.get("stages") or {}).items():
        mark = "ok" if outcome.get("success") else "FAILED"
        lines.append(f"  - {name}: {mark}")
        if outcome.get("message"):
            lines.append(f"      {outcome['message']}")
    return "\n".join(lines)
