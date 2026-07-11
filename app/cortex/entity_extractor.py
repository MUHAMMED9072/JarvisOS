from __future__ import annotations

from typing import Dict

from .intent_detector import Intent


class EntityExtractor:
    """
    Extracts entities from the user's command.
    """

    def extract(self, text: str, intent: Intent) -> Dict[str, str]:

        words = text.split()

        if intent == Intent.OPEN_APPLICATION:
            return {
                "application": " ".join(words[1:])
            }

        if intent == Intent.CLOSE_APPLICATION:
            return {
                "application": " ".join(words[1:])
            }

        if intent == Intent.SEARCH_WEB:
            return {
                "query": " ".join(words[1:])
            }

        return {}