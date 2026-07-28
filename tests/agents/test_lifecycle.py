from __future__ import annotations

import time

import pytest

from app.agents.base import AgentStatus
from app.agents.state_machine import AgentStateMachine, TransitionError, validate_transition, can_transition, allowed_transitions
from app.agents.lifecycle import LifecycleManager
from app.agents.types import SystemAgent


class TestValidateTransition:
    def test_valid_transition(self):
        # No exception expected
        validate_transition(AgentStatus.DESIGN, AgentStatus.BUILD)

    def test_invalid_transition(self):
        with pytest.raises(TransitionError, match="Illegal transition"):
            validate_transition(AgentStatus.DESIGN, AgentStatus.ACTIVE)

    def test_archived_no_transitions(self):
        assert allowed_transitions(AgentStatus.ARCHIVED) == []

    def test_can_transition_true(self):
        assert can_transition(AgentStatus.ACTIVE, AgentStatus.PAUSED) is True

    def test_can_transition_false(self):
        assert can_transition(AgentStatus.DESIGN, AgentStatus.ARCHIVED) is True
        assert can_transition(AgentStatus.DESIGN, AgentStatus.RETIRED) is False

    def test_allowed_from_design(self):
        allowed = allowed_transitions(AgentStatus.DESIGN)
        assert AgentStatus.BUILD in allowed
        assert AgentStatus.ARCHIVED in allowed

    def test_failed_can_recover(self):
        assert can_transition(AgentStatus.FAILED, AgentStatus.DESIGN) is True
        assert can_transition(AgentStatus.FAILED, AgentStatus.ARCHIVED) is True


class TestAgentStateMachine:
    def test_initial_state(self):
        sm = AgentStateMachine()
        assert sm.state == AgentStatus.DESIGN

    def test_transition(self):
        sm = AgentStateMachine()
        old = sm.transition(AgentStatus.BUILD)
        assert old == AgentStatus.DESIGN
        assert sm.state == AgentStatus.BUILD

    def test_transition_raises_on_illegal(self):
        sm = AgentStateMachine()
        with pytest.raises(TransitionError):
            sm.transition(AgentStatus.ACTIVE)

    def test_full_cycle(self):
        sm = AgentStateMachine()
        path = [
            AgentStatus.BUILD,
            AgentStatus.SANDBOX,
            AgentStatus.REVIEW,
            AgentStatus.APPROVED,
            AgentStatus.INSTALLED,
            AgentStatus.ACTIVE,
            AgentStatus.PAUSED,
            AgentStatus.ACTIVE,
            AgentStatus.RETIRED,
            AgentStatus.ARCHIVED,
        ]
        for target in path:
            sm.transition(target)
        assert sm.state == AgentStatus.ARCHIVED

    def test_history(self):
        sm = AgentStateMachine()
        sm.transition(AgentStatus.BUILD)
        sm.transition(AgentStatus.SANDBOX)
        h = sm.history()
        assert len(h) == 2

    def test_can_transition_to(self):
        sm = AgentStateMachine()
        assert sm.can_transition_to(AgentStatus.BUILD) is True
        assert sm.can_transition_to(AgentStatus.ACTIVE) is False

    def test_allowed_transitions(self):
        sm = AgentStateMachine()
        allowed = sm.allowed_transitions()
        assert AgentStatus.BUILD in allowed
        assert AgentStatus.ARCHIVED in allowed

    def test_reset(self):
        sm = AgentStateMachine()
        sm.transition(AgentStatus.BUILD)
        sm.reset()
        assert sm.state == AgentStatus.DESIGN
        assert len(sm.history()) == 0

    def test_health(self):
        sm = AgentStateMachine()
        h = sm.health()
        assert h["alive"] is True
        assert h["current_state"] == "design"

    def test_extended_transition_upgrade(self):
        sm = AgentStateMachine()
        sm.transition(AgentStatus.BUILD)
        sm.transition(AgentStatus.SANDBOX)
        sm.transition(AgentStatus.REVIEW)
        sm.transition(AgentStatus.APPROVED)
        sm.transition(AgentStatus.INSTALLED)
        sm.transition(AgentStatus.ACTIVE)
        old = sm.extended_transition("upgrade")
        assert old == AgentStatus.ACTIVE
        assert sm.state == AgentStatus.INSTALLED

    def test_extended_transition_invalid_op(self):
        sm = AgentStateMachine()
        assert sm.extended_transition("nonexistent") is None

    def test_extended_transition_wrong_state(self):
        sm = AgentStateMachine()
        with pytest.raises(TransitionError):
            sm.extended_transition("upgrade")  # needs ACTIVE, is DESIGN


class TestLifecycleManager:
    def test_initial_state(self):
        agent = SystemAgent()
        lm = LifecycleManager(agent)
        assert lm.state == AgentStatus.DESIGN

    def test_transition_updates_agent(self):
        agent = SystemAgent()
        lm = LifecycleManager(agent)
        lm.transition(AgentStatus.BUILD)
        assert agent.status == AgentStatus.BUILD

    def test_transition_events(self):
        events: list[str] = []
        def cb(event, data):
            events.append(event)
        agent = SystemAgent()
        lm = LifecycleManager(agent, event_callback=cb)
        lm.transition(AgentStatus.BUILD)
        assert len(events) == 1
        from app.agents.lifecycle import LifecycleEvent
        assert events[0] == LifecycleEvent.TRANSITIONED

    def test_allowed_transitions(self):
        agent = SystemAgent()
        lm = LifecycleManager(agent)
        allowed = lm.allowed_transitions()
        assert AgentStatus.BUILD in allowed

    def test_can_transition_to(self):
        agent = SystemAgent()
        lm = LifecycleManager(agent)
        assert lm.can_transition_to(AgentStatus.BUILD) is True
        assert lm.can_transition_to(AgentStatus.ACTIVE) is False

    def test_extended(self):
        agent = SystemAgent()
        lm = LifecycleManager(agent)
        for s in [AgentStatus.BUILD, AgentStatus.SANDBOX, AgentStatus.REVIEW,
                   AgentStatus.APPROVED, AgentStatus.INSTALLED, AgentStatus.ACTIVE]:
            lm.transition(s)
        assert lm.extended("upgrade") is not None
        assert lm.state == AgentStatus.INSTALLED

    def test_get_state_summary(self):
        agent = SystemAgent()
        lm = LifecycleManager(agent)
        summary = lm.get_state_summary()
        assert summary["agent_id"] == agent.agent_id
        assert summary["current_state"] == "design"

    def test_health(self):
        agent = SystemAgent()
        lm = LifecycleManager(agent)
        h = lm.health()
        assert h["alive"] is True

    def test_check_timeout_stalls_to_failed(self):
        agent = SystemAgent()
        lm = LifecycleManager(agent, timeout_seconds=0.01)
        time.sleep(0.02)
        assert lm.check_timeout() is True
        assert lm.state == AgentStatus.FAILED
