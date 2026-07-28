from __future__ import annotations

import pytest

from app.governance.policy_engine import PolicyEngine, PolicyDecision
from app.governance.policy_registry import (
    Policy,
    PolicyRule,
    PolicyAction,
    PolicyScope,
    PolicyRegistry,
)


class TestPolicyDecision:
    def test_default_action_deny(self):
        d = PolicyDecision()
        assert d.denied
        assert not d.allowed
        assert d.action == PolicyAction.DENY

    def test_allowed_property(self):
        d = PolicyDecision(action=PolicyAction.ALLOW)
        assert d.allowed
        assert not d.denied

    def test_flagged_property(self):
        d = PolicyDecision(action=PolicyAction.FLAG)
        assert d.flagged

    def test_requires_approval_property(self):
        d = PolicyDecision(action=PolicyAction.REQUIRE_APPROVAL)
        assert d.requires_approval

    def test_to_dict(self):
        d = PolicyDecision(action=PolicyAction.ALLOW, reason="ok")
        result = d.to_dict()
        assert result["action"] == "allow"
        assert result["allowed"]


class TestPolicyEngine:
    def test_default_registry_created(self):
        engine = PolicyEngine()
        assert engine.registry is not None
        assert engine.registry.count() == 0

    def test_evaluate_no_policies_allows(self):
        engine = PolicyEngine()
        decision = engine.evaluate({"scope": "agent"})
        assert decision.allowed
        assert decision.reason == "All policies allow this operation"

    def test_deny_policy(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="deny-all",
            rules=[PolicyRule(condition="", action=PolicyAction.DENY, reason="denied")],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        decision = engine.evaluate({"scope": "agent"})
        assert decision.denied
        assert "denied" in decision.reason

    def test_allow_policy(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="allow-all",
            rules=[PolicyRule(condition="", action=PolicyAction.ALLOW, reason="allowed")],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        decision = engine.evaluate({"scope": "agent"})
        assert decision.allowed

    def test_deny_overrides_allow(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="allow-low",
            rules=[PolicyRule(condition="", action=PolicyAction.ALLOW)],
            priority=1,
        ))
        registry.register(Policy(
            name="deny-high",
            rules=[PolicyRule(condition="", action=PolicyAction.DENY, reason="deny")],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        decision = engine.evaluate({"scope": "agent"})
        assert decision.denied

    def test_flag_policy(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="flag-high",
            rules=[PolicyRule(condition="", action=PolicyAction.FLAG, reason="flagged")],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        decision = engine.evaluate({"scope": "agent"})
        assert decision.flagged

    def test_require_approval_policy(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="approval-needed",
            rules=[PolicyRule(condition="", action=PolicyAction.REQUIRE_APPROVAL, reason="needs approval")],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        decision = engine.evaluate({"scope": "agent"})
        assert decision.requires_approval

    def test_condition_matching(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="admin-only",
            rules=[
                PolicyRule(condition="role == admin", action=PolicyAction.ALLOW, reason="admin ok"),
                PolicyRule(condition="", action=PolicyAction.DENY, reason="not admin"),
            ],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        decision_admin = engine.evaluate({"scope": "agent", "role": "admin"})
        assert decision_admin.allowed
        decision_user = engine.evaluate({"scope": "agent", "role": "user"})
        assert not decision_user.allowed

    def test_condition_not_equal(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="block-guest",
            rules=[
                PolicyRule(condition="role != guest", action=PolicyAction.ALLOW, reason="not guest"),
                PolicyRule(condition="", action=PolicyAction.DENY, reason="guest"),
            ],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        assert engine.evaluate({"scope": "agent", "role": "admin"}).allowed
        assert engine.evaluate({"scope": "agent", "role": "guest"}).denied

    def test_condition_greater_than(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="resource-limit",
            rules=[PolicyRule(condition="cpu > 50", action=PolicyAction.DENY, reason="cpu too high")],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        assert engine.evaluate({"scope": "agent", "cpu": 80}).denied
        assert engine.evaluate({"scope": "agent", "cpu": 20}).allowed

    def test_disabled_policy_not_evaluated(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="deny-all",
            enabled=False,
            rules=[PolicyRule(condition="", action=PolicyAction.DENY)],
        ))
        engine = PolicyEngine(registry)
        decision = engine.evaluate({"scope": "agent"})
        assert decision.allowed

    def test_scope_filtering(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="agent-only",
            scope=PolicyScope.AGENT,
            rules=[PolicyRule(condition="", action=PolicyAction.DENY, reason="agent policy")],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        decision_agent = engine.evaluate({"scope": "agent"})
        assert decision_agent.denied
        decision_system = engine.evaluate({"scope": "system"})
        assert decision_system.allowed

    def test_global_scope_matches_all(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="global-deny",
            scope=PolicyScope.GLOBAL,
            rules=[PolicyRule(condition="", action=PolicyAction.DENY, reason="global")],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        assert engine.evaluate({"scope": "agent"}).denied
        assert engine.evaluate({"scope": "system"}).denied

    def test_nested_field_resolution(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="nested-check",
            rules=[
                PolicyRule(condition="metadata.trust_level == high", action=PolicyAction.ALLOW),
                PolicyRule(condition="", action=PolicyAction.DENY),
            ],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        assert engine.evaluate({"scope": "agent", "metadata": {"trust_level": "high"}}).allowed
        assert engine.evaluate({"scope": "agent", "metadata": {"trust_level": "low"}}).denied

    def test_no_rules_matched(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="strict",
            rules=[PolicyRule(condition="role == superadmin", action=PolicyAction.DENY)],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        decision = engine.evaluate({"scope": "agent", "role": "user"})
        assert decision.allowed

    def test_multiple_conditions_in_order(self):
        registry = PolicyRegistry()
        registry.register(Policy(
            name="multi-rule",
            rules=[
                PolicyRule(condition="role == blocked", action=PolicyAction.DENY, reason="blocked"),
                PolicyRule(condition="role == admin", action=PolicyAction.ALLOW, reason="admin ok"),
            ],
            priority=10,
        ))
        engine = PolicyEngine(registry)
        assert engine.evaluate({"scope": "agent", "role": "blocked"}).denied
        assert engine.evaluate({"scope": "agent", "role": "admin"}).allowed
        assert engine.evaluate({"scope": "agent", "role": "user"}).allowed

    def test_get_stats(self):
        registry = PolicyRegistry()
        registry.register(Policy(name="p1"))
        engine = PolicyEngine(registry)
        stats = engine.get_stats()
        assert stats["policies_registered"] == 1
        assert stats["evaluations_performed"] == 0
        engine.evaluate({"scope": "agent"})
        stats = engine.get_stats()
        assert stats["evaluations_performed"] == 1

    def test_health(self):
        engine = PolicyEngine()
        h = engine.health()
        assert h["alive"]
        assert h["policies"] == 0

    def test_resolve_field_none(self):
        engine = PolicyEngine()
        result = engine._resolve_field("missing.key", {"scope": "agent"})
        assert result is None

    def test_coerce_bool(self):
        engine = PolicyEngine()
        assert engine._coerce("true", bool) is True
        assert engine._coerce("false", bool) is False

    def test_coerce_int(self):
        engine = PolicyEngine()
        assert engine._coerce("42", int) == 42

    def test_coerce_float(self):
        engine = PolicyEngine()
        assert engine._coerce("3.14", float) == 3.14

    def test_thread_safe(self):
        import threading
        registry = PolicyRegistry()
        registry.register(Policy(
            name="allow-all",
            rules=[PolicyRule(condition="", action=PolicyAction.ALLOW)],
            priority=0,
        ))
        engine = PolicyEngine(registry)
        errors = []

        def eval():
            try:
                for _ in range(50):
                    engine.evaluate({"scope": "agent"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=eval) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
