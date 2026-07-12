from app.memory.storage import MemoryStorage

db = MemoryStorage("history.json")

db.set("user", "Muhammed")

print(db.get("user"))
