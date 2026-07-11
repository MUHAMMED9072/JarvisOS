from __future__ import annotations

from enum import Enum


class Intent(Enum):
    OPEN_APPLICATION = "open_application"
    CLOSE_APPLICATION = "close_application"
    SEARCH_WEB = "search_web"
    MEMORY_RECALL = "memory_recall"
    CHAT = "chat"
    UNKNOWN = "unknown"


class IntentDetector:
    """
    Detects the user's intent from normalized text.
    """

    def detect(self, text: str) -> tuple[Intent, float]:

        text = text.lower().strip()

        if not text:
            return Intent.UNKNOWN, 0.0

        words = text.split()

        # ----------------------------
        # Memory Recall
        # ----------------------------

        memory_phrases = (
            "last application",
            "last app",
            "last command",
            "last request",
            "what did i ask",
            "what did you remember",
            "what do you remember",
            "what was the last application",
            "what was my last command",
        )

        if any(phrase in text for phrase in memory_phrases):
            return Intent.MEMORY_RECALL, 0.99

        # ----------------------------
        # Open Application
        # ----------------------------

        if words[0] == "open":
            return Intent.OPEN_APPLICATION, 0.98

        # ----------------------------
        # Close Application
        # ----------------------------

        if words[0] == "close":
            return Intent.CLOSE_APPLICATION, 0.98

        # ----------------------------
        # Search Web
        # ----------------------------

        if words[0] == "search":
            return Intent.SEARCH_WEB, 0.95

        # ----------------------------
        # Default
        # ----------------------------

        return Intent.CHAT, 0.75