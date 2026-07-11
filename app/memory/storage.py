import json
from pathlib import Path

from .models import MemoryItem


class MemoryStorage:
    """
    Handles persistent memory storage using JSON.
    """

    def __init__(self, filepath: str = "data/memory.json"):
        self.filepath = Path(filepath)

        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        if not self.filepath.exists():
            self.clear()

    def load(self) -> list[dict]:
        """
        Load all stored memories.
        """

        try:
            with self.filepath.open("r", encoding="utf-8") as file:
                return json.load(file)

        except (json.JSONDecodeError, FileNotFoundError):
            self.clear()
            return []

    def save_all(self, memories: list[dict]) -> None:
        """
        Save the complete memory list.
        """

        with self.filepath.open("w", encoding="utf-8") as file:
            json.dump(
                memories,
                file,
                indent=4,
                ensure_ascii=False,
            )

    def save_item(self, item: MemoryItem) -> None:
        """
        Append one memory item.
        """

        memories = self.load()
        memories.append(item.to_dict())
        self.save_all(memories)

    def clear(self) -> None:
        """
        Clear all stored memories.
        """

        self.save_all([])