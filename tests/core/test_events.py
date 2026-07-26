"""Tests for core event name constants."""

from __future__ import annotations

from app.core.events import AIEvents


class TestAIEvents:
    """Validate AI event name constants."""

    def test_request_event(self):
        assert AIEvents.REQUEST == "ai.request"

    def test_response_event(self):
        assert AIEvents.RESPONSE == "ai.response"

    def test_stream_start_event(self):
        assert AIEvents.STREAM_START == "ai.stream.start"

    def test_stream_complete_event(self):
        assert AIEvents.STREAM_COMPLETE == "ai.stream.complete"

    def test_stream_cancel_event(self):
        assert AIEvents.STREAM_CANCEL == "ai.stream.cancel"

    def test_plan_start_event(self):
        assert AIEvents.PLAN_START == "ai.plan.start"

    def test_plan_complete_event(self):
        assert AIEvents.PLAN_COMPLETE == "ai.plan.complete"

    def test_plan_fail_event(self):
        assert AIEvents.PLAN_FAIL == "ai.plan.fail"

    def test_reason_start_event(self):
        assert AIEvents.REASON_START == "ai.reason.start"

    def test_reason_complete_event(self):
        assert AIEvents.REASON_COMPLETE == "ai.reason.complete"

    def test_reason_fail_event(self):
        assert AIEvents.REASON_FAIL == "ai.reason.fail"

    def test_tool_call_event(self):
        assert AIEvents.TOOL_CALL == "ai.tool.call"

    def test_tool_result_event(self):
        assert AIEvents.TOOL_RESULT == "ai.tool.result"

    def test_conversation_create_event(self):
        assert AIEvents.CONVERSATION_CREATE == "ai.conversation.create"

    def test_conversation_message_event(self):
        assert AIEvents.CONVERSATION_MESSAGE == "ai.conversation.message"

    def test_memory_store_event(self):
        assert AIEvents.MEMORY_STORE == "ai.memory.store"

    def test_memory_retrieve_event(self):
        assert AIEvents.MEMORY_RETRIEVE == "ai.memory.retrieve"

    def test_all_events_are_strings(self):
        for attr in dir(AIEvents):
            if not attr.startswith("_"):
                assert isinstance(getattr(AIEvents, attr), str)

    def test_all_events_have_ai_prefix(self):
        for attr in dir(AIEvents):
            if not attr.startswith("_"):
                assert getattr(AIEvents, attr).startswith("ai.")

    def test_no_duplicate_values(self):
        values = {
            getattr(AIEvents, attr)
            for attr in dir(AIEvents)
            if not attr.startswith("_")
        }
        # Each value should be unique
        assert len(values) == sum(
            1 for attr in dir(AIEvents) if not attr.startswith("_")
        )
