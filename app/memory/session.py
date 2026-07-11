from collections import deque


class SessionMemory:
    """
    Stores temporary conversation context while JARVIS is running.
    """

    def __init__(self, max_history: int = 20):
        self.messages = deque(maxlen=max_history)

        self.last_intent: str | None = None
        self.last_entities: dict = {}
        self.last_application: str | None = None
        self.last_skill: str | None = None

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    def get_messages(self) -> list[dict]:
        return list(self.messages)

    def set_context(
        self,
        *,
        intent: str | None = None,
        entities: dict | None = None,
        skill: str | None = None,
    ) -> None:

        if intent is not None:
            self.last_intent = intent

        if entities is not None:
            self.last_entities = entities

            app = entities.get("application")

            if app:
                self.last_application = app

        if skill is not None:
            self.last_skill = skill

    def clear(self) -> None:
        self.messages.clear()

        self.last_intent = None
        self.last_entities = {}
        self.last_application = None
        self.last_skill = None