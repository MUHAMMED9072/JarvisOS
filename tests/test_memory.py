from app.memory import MemoryStorage
from app.memory.models import MemoryItem

memory = MemoryStorage()
memory.clear()

memory.save_item(MemoryItem.create(
    role="user",
    content="Open Chrome"
))

memory.save_item(MemoryItem.create(
    role="assistant",
    content="Chrome opened."
))

memory.save_item(MemoryItem.create(
    role="user",
    content="Open VS Code"
))

for item in memory.load():
    print(item)