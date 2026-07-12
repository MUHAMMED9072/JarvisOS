from __future__ import annotations

import json
from pathlib import Path


class MemoryStorage:

    def __init__(self, filename: str):

        self.path = Path("data") / "memory" / filename

        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            self.save({})

    def load(self) -> dict:

        try:

            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)

        except Exception:
            return {}

    def save(self, data: dict):

        with open(self.path, "w", encoding="utf-8") as f:

            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False,
            )

    def get(self, key, default=None):

        return self.load().get(key, default)

    def set(self, key, value):

        data = self.load()

        data[key] = value

        self.save(data)

    def delete(self, key):

        data = self.load()

        if key in data:

            del data[key]

            self.save(data)

    def clear(self):

        self.save({})