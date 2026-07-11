from __future__ import annotations

from .models import BrainType
from .intent_detector import Intent


class BrainSelector:
    """
    Selects which brain should handle the request.
    """

    def select(self, intent: Intent) -> BrainType:

        if intent in (
            Intent.OPEN_APPLICATION,
            Intent.CLOSE_APPLICATION,
            Intent.SEARCH_WEB,
        ):
            return BrainType.FAST

        if intent == Intent.CHAT:
            return BrainType.SMART

        return BrainType.DEEP