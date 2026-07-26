from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence


@dataclass
class ConversationMessage:
    role: str = "user"
    content: str = ""
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    metadata: dict = field(default_factory=dict)


@dataclass
class Conversation:
    conversation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    messages: list[ConversationMessage] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    metadata: dict = field(default_factory=dict)
    max_messages: int = 50
    system_prompt: str = ""


class ConversationManager:

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def create(
        self,
        provider: str = "",
        model: str = "",
        system_prompt: str = "",
        max_messages: int = 50,
        metadata: dict | None = None,
    ) -> Conversation:
        conv = Conversation(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            max_messages=max_messages,
            metadata=metadata or {},
        )
        self._conversations[conv.conversation_id] = conv
        return conv

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def get_or_create(
        self,
        conversation_id: str,
        provider: str = "",
        model: str = "",
        system_prompt: str = "",
    ) -> Conversation:
        existing = self.get(conversation_id)
        if existing is not None:
            return existing
        conv = Conversation(
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            system_prompt=system_prompt,
        )
        self._conversations[conv.conversation_id] = conv
        return conv

    def delete(self, conversation_id: str) -> bool:
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    def clear(self, conversation_id: str) -> bool:
        conv = self.get(conversation_id)
        if conv is None:
            return False
        conv.messages.clear()
        conv.updated_at = datetime.now(timezone.utc).timestamp()
        return True

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> ConversationMessage | None:
        conv = self.get(conversation_id)
        if conv is None:
            return None
        msg = ConversationMessage(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        conv.messages.append(msg)
        conv.updated_at = datetime.now(timezone.utc).timestamp()
        self._trim(conv)
        return msg

    def list_messages(
        self,
        conversation_id: str,
    ) -> Sequence[ConversationMessage]:
        conv = self.get(conversation_id)
        if conv is None:
            return ()
        return list(conv.messages)

    def set_metadata(
        self,
        conversation_id: str,
        key: str,
        value: object,
    ) -> bool:
        conv = self.get(conversation_id)
        if conv is None:
            return False
        conv.metadata[key] = value
        return True

    def update_timestamp(self, conversation_id: str) -> bool:
        conv = self.get(conversation_id)
        if conv is None:
            return False
        conv.updated_at = datetime.now(timezone.utc).timestamp()
        return True

    @property
    def active_count(self) -> int:
        return len(self._conversations)

    @staticmethod
    def _trim(conv: Conversation) -> None:
        if len(conv.messages) <= conv.max_messages:
            return
        system_msgs = [
            m for m in conv.messages if m.role == "system"
        ]
        non_system = [
            m for m in conv.messages if m.role != "system"
        ]
        excess = len(non_system) - (conv.max_messages - len(system_msgs))
        if excess > 0:
            conv.messages = system_msgs + non_system[excess:]
