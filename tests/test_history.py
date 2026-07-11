from app.memory import MemoryStorage
from app.memory.history import MemoryHistory
from app.memory.models import MemoryItem

storage = MemoryStorage()
storage.clear()

storage.save_item(
    MemoryItem.create("user", "Open Chrome")
)

storage.save_item(
    MemoryItem.create("assistant", "Chrome opened.")
)

storage.save_item(
    MemoryItem.create("user", "Open VS Code")
)

history = MemoryHistory(storage)

print("\nALL")
print(history.get_all())

print("\nRECENT")
print(history.get_recent(2))

print("\nSEARCH")
print(history.search("chrome"))

print("\nLAST USER")
print(history.last_user_message())

print("\nLAST ASSISTANT")
print(history.last_assistant_message())