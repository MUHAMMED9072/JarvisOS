from __future__ import annotations

import re


class Normalizer:
    """
    Cleans and standardizes user input.
    """

    WAKE_WORDS = (
        "jarvis",
        "hey jarvis",
        "ok jarvis",
    )

    SYNONYMS = {
        "launch": "open",
        "start": "open",
        "run": "open",
        "execute": "open",
    }

    def process(self, text: str) -> str:

        text = text.lower().strip()

        # Remove wake words
        for wake in self.WAKE_WORDS:
            if text.startswith(wake):
                text = text[len(wake):].strip(" ,")

        # Remove punctuation
        text = re.sub(r"[^\w\s]", "", text)

        # Normalize spaces
        text = re.sub(r"\s+", " ", text).strip()

        # Replace synonyms
        words = [
            self.SYNONYMS.get(word, word)
            for word in text.split()
        ]

        return " ".join(words)