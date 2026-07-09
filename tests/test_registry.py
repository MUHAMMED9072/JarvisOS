from app.services import registry


class DummyAI:
    def chat(self):
        return "Hello."


registry.register("ai", DummyAI())

print(registry.list_services())

ai = registry.get("ai")

print(ai.chat())
