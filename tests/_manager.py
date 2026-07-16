"""
Manual regression check for ROADMAP.md P0 1a-1c / MEMORY_SYSTEM.md's
three-link MemoryManager failure chain:

  Link 1: ImportError on MemoryItem     (app/memory/models.py)
  Link 2: TypeError on MemoryStorage()  (app/memory/manager.py __init__)
  Link 3: AttributeError on save_item   (app/memory/manager.py remember)

Run with: PYTHONPATH=. python3 tests/_manager.py
"""

from app.memory.manager import MemoryManager


def main() -> None:
    manager = MemoryManager()

    manager.remember("user", "hello jarvis")
    manager.remember("assistant", "hello, how can I help?")

    items = manager.storage.get("items", [])

    assert len(items) == 2, f"expected 2 stored items, got {len(items)}"
    assert items[0]["role"] == "user"
    assert items[0]["content"] == "hello jarvis"
    assert items[1]["role"] == "assistant"
    assert items[1]["content"] == "hello, how can I help?"

    manager.storage.delete("items")

    print("MemoryManager import/construct/remember() chain: OK")


if __name__ == "__main__":
    main()