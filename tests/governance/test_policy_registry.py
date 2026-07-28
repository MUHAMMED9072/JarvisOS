from __future__ import annotations

import pytest

from app.governance.policy_registry import (
    Policy,
    PolicyRule,
    PolicyAction,
    PolicyScope,
    PolicyRegistry,
)


class TestPolicy:
    def test_default_id_generated(self):
        p = Policy(name="test")
        assert len(p.id) == 16

    def test_to_dict_roundtrip(self):
        p = Policy(
            name="test-policy",
            description="Test",
            scope=PolicyScope.SYSTEM,
            rules=[PolicyRule(condition="role == admin", action=PolicyAction.ALLOW)],
            priority=10,
        )
        d = p.to_dict()
        assert d["name"] == "test-policy"
        assert d["scope"] == "system"
        assert len(d["rules"]) == 1
        assert d["rules"][0]["condition"] == "role == admin"

    def test_policy_rule_defaults(self):
        r = PolicyRule()
        assert r.condition == ""
        assert r.action == PolicyAction.DENY
        assert r.severity == 2

    def test_policy_rule_to_dict(self):
        r = PolicyRule(condition="x > 1", action=PolicyAction.FLAG, reason="flagged", severity=3)
        d = r.to_dict()
        assert d["condition"] == "x > 1"
        assert d["action"] == "flag"
        assert d["reason"] == "flagged"
        assert d["severity"] == 3


class TestPolicyRegistry:
    def test_register_and_get(self):
        reg = PolicyRegistry()
        p = Policy(name="p1")
        pid = reg.register(p)
        assert reg.get(pid) is p

    def test_register_and_get_by_name(self):
        reg = PolicyRegistry()
        p = Policy(name="unique-name")
        reg.register(p)
        assert reg.get_by_name("unique-name") is p

    def test_get_by_name_not_found(self):
        reg = PolicyRegistry()
        assert reg.get_by_name("nonexistent") is None

    def test_get_missing(self):
        reg = PolicyRegistry()
        assert reg.get("missing") is None

    def test_update(self):
        reg = PolicyRegistry()
        p = Policy(name="p1", description="old")
        pid = reg.register(p)
        p.description = "new"
        assert reg.update(p)
        assert reg.get(pid).description == "new"

    def test_update_missing(self):
        reg = PolicyRegistry()
        p = Policy(name="p1")
        assert not reg.update(p)

    def test_delete(self):
        reg = PolicyRegistry()
        pid = reg.register(Policy(name="p1"))
        assert reg.delete(pid)
        assert reg.get(pid) is None

    def test_delete_missing(self):
        reg = PolicyRegistry()
        assert not reg.delete("missing")

    def test_list_policies_empty(self):
        reg = PolicyRegistry()
        assert reg.list_policies() == []

    def test_list_policies_sorted_by_priority(self):
        reg = PolicyRegistry()
        p1 = Policy(name="low", priority=1)
        p2 = Policy(name="high", priority=10)
        reg.register(p1)
        reg.register(p2)
        items = reg.list_policies()
        assert items[0].name == "high"
        assert items[1].name == "low"

    def test_list_policies_filter_scope(self):
        reg = PolicyRegistry()
        reg.register(Policy(name="sys", scope=PolicyScope.SYSTEM))
        reg.register(Policy(name="agt", scope=PolicyScope.AGENT))
        items = reg.list_policies(scope=PolicyScope.SYSTEM)
        assert len(items) == 1
        assert items[0].name == "sys"

    def test_list_policies_enabled_only(self):
        reg = PolicyRegistry()
        reg.register(Policy(name="enabled", enabled=True))
        reg.register(Policy(name="disabled", enabled=False))
        items = reg.list_policies(enabled_only=True)
        assert len(items) == 1
        assert items[0].name == "enabled"

    def test_count(self):
        reg = PolicyRegistry()
        assert reg.count() == 0
        reg.register(Policy(name="p1"))
        assert reg.count() == 1

    def test_clear(self):
        reg = PolicyRegistry()
        reg.register(Policy(name="p1"))
        reg.clear()
        assert reg.count() == 0

    def test_thread_safe(self):
        import threading
        reg = PolicyRegistry()
        errors = []

        def add():
            try:
                for i in range(100):
                    reg.register(Policy(name=f"p{i}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert reg.count() == 400
