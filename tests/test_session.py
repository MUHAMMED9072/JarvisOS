from app.memory.session import SessionMemory

session = SessionMemory()

session.set_context(
    intent="open_application",
    entities={
        "application": "chrome"
    }
)

print("Last app:", session.last_application)

user_command = "Close it"

if "it" in user_command.lower():
    print("Resolved to:", session.last_application)