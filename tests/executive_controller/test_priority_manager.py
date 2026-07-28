from __future__ import annotations

import threading

import pytest

from app.executive_controller.priority_manager import PriorityLevel, PriorityManager


class TestPriorityLevel:
    def test_ordering(self) -> None:
        assert PriorityLevel.CRITICAL < PriorityLevel.HIGH
        assert PriorityLevel.HIGH < PriorityLevel.MEDIUM
        assert PriorityLevel.MEDIUM < PriorityLevel.LOW
        assert PriorityLevel.LOW < PriorityLevel.BACKGROUND


class TestPriorityManager:
    def test_set_and_get(self) -> None:
        pm = PriorityManager()
        pm.set_priority("agent-a", PriorityLevel.HIGH)
        assert pm.get_priority("agent-a") == PriorityLevel.HIGH

    def test_default_is_medium(self) -> None:
        pm = PriorityManager()
        assert pm.get_priority("unknown") == PriorityLevel.MEDIUM

    def test_get_after_unset(self) -> None:
        pm = PriorityManager()
        pm.set_priority("agent-a", PriorityLevel.HIGH)
        pm.unset_priority("agent-a")
        assert pm.get_priority("agent-a") == PriorityLevel.MEDIUM

    def test_unset_missing_returns_false(self) -> None:
        pm = PriorityManager()
        assert pm.unset_priority("nonexistent") is False

    def test_inherit_simple(self) -> None:
        pm = PriorityManager()
        pm.set_priority("parent", PriorityLevel.CRITICAL)
        pm.inherit("child", "parent")
        assert pm.get_priority("child") == PriorityLevel.CRITICAL

    def test_inherit_chain(self) -> None:
        pm = PriorityManager()
        pm.set_priority("grandparent", PriorityLevel.HIGH)
        pm.inherit("parent", "grandparent")
        pm.inherit("child", "parent")
        assert pm.get_priority("child") == PriorityLevel.HIGH

    def test_inherit_overrides_own_priority(self) -> None:
        pm = PriorityManager()
        pm.set_priority("parent", PriorityLevel.CRITICAL)
        pm.set_priority("child", PriorityLevel.LOW)
        pm.inherit("child", "parent")
        assert pm.get_priority("child") == PriorityLevel.CRITICAL

    def test_uninherit_reverts_to_own(self) -> None:
        pm = PriorityManager()
        pm.set_priority("parent", PriorityLevel.CRITICAL)
        pm.set_priority("child", PriorityLevel.LOW)
        pm.inherit("child", "parent")
        assert pm.get_priority("child") == PriorityLevel.CRITICAL
        pm.uninherit("child")
        assert pm.get_priority("child") == PriorityLevel.LOW

    def test_uninherit_missing_returns_false(self) -> None:
        pm = PriorityManager()
        assert pm.uninherit("nonexistent") is False

    def test_get_children(self) -> None:
        pm = PriorityManager()
        pm.inherit("child1", "parent")
        pm.inherit("child2", "parent")
        assert sorted(pm.get_children("parent")) == ["child1", "child2"]

    def test_get_children_empty(self) -> None:
        pm = PriorityManager()
        assert pm.get_children("no-children") == []

    def test_get_all(self) -> None:
        pm = PriorityManager()
        pm.set_priority("a", PriorityLevel.HIGH)
        pm.set_priority("b", PriorityLevel.LOW)
        all_p = pm.get_all()
        assert all_p["a"] == PriorityLevel.HIGH
        assert all_p["b"] == PriorityLevel.LOW

    def test_to_dict(self) -> None:
        pm = PriorityManager()
        pm.set_priority("a", PriorityLevel.CRITICAL)
        pm.inherit("b", "a")
        d = pm.to_dict()
        assert d["priorities"]["a"] == "CRITICAL"
        assert d["inheritance"]["b"] == "a"

    def test_circular_inheritance_returns_medium(self) -> None:
        pm = PriorityManager()
        pm.set_priority("x", PriorityLevel.HIGH)
        pm.inherit("x", "y")
        pm.inherit("y", "x")
        assert pm.get_priority("x") == PriorityLevel.MEDIUM

    def test_thread_safety(self) -> None:
        pm = PriorityManager()
        errors: list[Exception] = []

        def worker() -> None:
            for i in range(100):
                try:
                    pm.set_priority(f"agent-{i}", PriorityLevel.HIGH)
                    pm.get_priority(f"agent-{i}")
                    pm.get_all()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
