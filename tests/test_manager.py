from app.memory import MemoryManager

memory = MemoryManager()

memory.clear()

memory.remember(
    role="user",
    content="Open Chrome",
)

memory.set_context(
    intent="open_application",
    entities={
        "application": "chrome"
    },
    skill="application_launcher"
)

memory.remember(
    role="assistant",
    content="Chrome opened."
)

print("\nSESSION")
print(memory.get_session_messages())

print("\nRECENT")
print(memory.get_recent())

print("\nSEARCH")
print(memory.search("chrome"))

print("\nLAST APPLICATION")
print(memory.session.last_application)

print("\nLAST INTENT")
print(memory.session.last_intent)