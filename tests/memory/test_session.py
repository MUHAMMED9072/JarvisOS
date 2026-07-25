from __future__ import annotations

import pytest

from app.memory.session import SessionMemory


class TestSessionMemory:
    @pytest.fixture
    def session(self):
        return SessionMemory(max_history=5)

    # ------------------------------------------------------------------
    # add_message / get_messages
    # ------------------------------------------------------------------

    def test_add_message_appends(self, session):
        session.add_message("user", "hello")
        msgs = session.get_messages()
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "hello"}

    def test_add_message_multiple(self, session):
        session.add_message("user", "hi")
        session.add_message("assistant", "hello")
        msgs = session.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_max_history_enforced(self, session):
        for i in range(10):
            session.add_message("user", f"msg {i}")
        assert len(session.get_messages()) == 5

    def test_max_history_drops_oldest(self, session):
        for i in range(6):
            session.add_message("user", f"msg {i}")
        msgs = session.get_messages()
        assert msgs[0]["content"] == "msg 1"
        assert msgs[-1]["content"] == "msg 5"

    # ------------------------------------------------------------------
    # set_context
    # ------------------------------------------------------------------

    def test_set_context_intent(self, session):
        session.set_context(intent="test_intent")
        assert session.last_intent == "test_intent"

    def test_set_context_entities(self, session):
        session.set_context(entities={"key": "val"})
        assert session.last_entities == {"key": "val"}

    def test_set_context_entities_extracts_application(self, session):
        session.set_context(entities={"application": "notepad"})
        assert session.last_application == "notepad"

    def test_set_context_skill(self, session):
        session.set_context(skill="test_skill")
        assert session.last_skill == "test_skill"

    def test_set_context_partial_update(self, session):
        session.set_context(intent="first", skill="first_skill")
        session.set_context(intent="second")
        assert session.last_intent == "second"
        assert session.last_skill == "first_skill"

    def test_set_context_no_entities_keeps_previous(self, session):
        session.set_context(entities={"app": "calc"})
        session.set_context(intent="other")
        assert session.last_entities == {"app": "calc"}

    # ------------------------------------------------------------------
    # clear
    # ------------------------------------------------------------------

    def test_clear_removes_messages(self, session):
        session.add_message("user", "hello")
        session.clear()
        assert session.get_messages() == []

    def test_clear_resets_context(self, session):
        session.set_context(intent="test", entities={"app": "calc"}, skill="skill1")
        session.clear()
        assert session.last_intent is None
        assert session.last_entities == {}
        assert session.last_application is None
        assert session.last_skill is None

    # ------------------------------------------------------------------
    # get_messages returns a copy
    # ------------------------------------------------------------------

    def test_get_messages_returns_copy(self, session):
        session.add_message("user", "hello")
        msgs = session.get_messages()
        msgs.append({"role": "assistant", "content": "world"})
        assert len(session.get_messages()) == 1
