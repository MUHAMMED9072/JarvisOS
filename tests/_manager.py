"""
Manual regression check for:

  ROADMAP.md P0 1a-1c / MEMORY_SYSTEM.md's three-link MemoryManager chain:
    Link 1: ImportError on MemoryItem     (app/memory/models.py)
    Link 2: TypeError on MemoryStorage()  (app/memory/manager.py __init__)
    Link 3: AttributeError on save_item   (app/memory/manager.py remember)

  ROADMAP.md P0 2 / MEMORY_SYSTEM.md's Secondary Bug:
    MemoryHistory assumed storage.load() (a dict) was a list.
    (app/memory/history.py)

Run with: PYTHONPATH=. python3 tests/_manager.py
"""

from app.memory.manager import MemoryManager


def check_remember_chain() -> None:
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


def check_history_reads() -> None:
    manager = MemoryManager()

    manager.remember("user", "hello jarvis")
    manager.remember("assistant", "hi there")
    manager.remember(
        "user",
        "open notepad",
        metadata={"entities": {"application": "notepad"}},
    )

    recent = manager.get_recent(2)
    assert len(recent) == 2, f"expected 2 recent items, got {len(recent)}"
    assert recent[-1]["content"] == "open notepad"

    found = manager.search("open")
    assert len(found) == 1, f"expected 1 search hit, got {len(found)}"
    assert found[0]["content"] == "open notepad"

    last_user = manager.history.last_user_message()
    assert last_user is not None and last_user["content"] == "open notepad"

    last_assistant = manager.history.last_assistant_message()
    assert last_assistant is not None and last_assistant["content"] == "hi there"

    all_items = manager.history.get_all()
    assert len(all_items) == 3, f"expected 3 total items, got {len(all_items)}"

    assert manager.get_last_application() == "notepad"

    manager.storage.delete("items")

    print("MemoryHistory get_recent/search/last_*/get_all chain: OK")


def main() -> None:
    check_remember_chain()
    check_history_reads()


if __name__ == "__main__":
    main()