from app.skills.base import Skill


class ChatSkill(Skill):

    name = "Chat Skill"
    intent = "chat"
    version = "1.0.0"
    description = "Conversational AI"

    _conversation_id: str | None = None

    def run(self, request):
        if self._conversation_id is None:
            conv = self.create_conversation()
            if conv is not None:
                self._conversation_id = conv.conversation_id
        return self.ask(
            request.text,
            conversation_id=self._conversation_id,
        )