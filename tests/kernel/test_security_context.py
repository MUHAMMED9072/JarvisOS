"""Tests for SecurityContext and SecurityContextVar."""

from __future__ import annotations

import threading

import pytest

from app.kernel.security.context import (
    SecurityContext,
    SecurityContextVar,
    require_permission,
)


class TestSecurityContext:
    def test_default_actor_is_anonymous(self):
        ctx = SecurityContext()
        assert ctx.actor == "anonymous"

    def test_actor_set_via_constructor(self):
        ctx = SecurityContext(actor="user:alice")
        assert ctx.actor == "user:alice"

    def test_granted_empty_by_default(self):
        ctx = SecurityContext()
        assert ctx.granted == frozenset()

    def test_granted_from_constructor(self):
        ctx = SecurityContext(granted={"ai.ask", "memory.read"})
        assert ctx.granted == frozenset({"ai.ask", "memory.read"})

    def test_check_returns_true_for_granted(self):
        ctx = SecurityContext(granted={"ai.ask"})
        assert ctx.check("ai.ask") is True

    def test_check_returns_false_for_not_granted(self):
        ctx = SecurityContext(granted={"memory.read"})
        assert ctx.check("ai.ask") is False

    def test_check_returns_false_for_empty(self):
        ctx = SecurityContext()
        assert ctx.check("ai.ask") is False

    def test_require_passes_for_granted(self):
        ctx = SecurityContext(granted={"ai.ask"})
        ctx.require("ai.ask")

    def test_require_raises_for_not_granted(self):
        ctx = SecurityContext(granted={"memory.read"})
        with pytest.raises(PermissionError):
            ctx.require("ai.ask")

    def test_require_raises_for_empty(self):
        ctx = SecurityContext()
        with pytest.raises(PermissionError):
            ctx.require("ai.ask")

    def test_copy_creates_independent_context(self):
        ctx = SecurityContext(actor="user:alice", granted={"ai.ask"})
        copied = ctx.copy()
        assert copied.actor == "user:alice"
        assert copied.granted == frozenset({"ai.ask"})
        # Modifying original should not affect copy
        ctx2 = ctx.merge({"memory.read"})
        assert copied.granted != ctx2.granted

    def test_merge_adds_permissions(self):
        ctx = SecurityContext(granted={"ai.ask"})
        merged = ctx.merge({"memory.read"})
        assert merged.granted == frozenset({"ai.ask", "memory.read"})

    def test_merge_does_not_modify_original(self):
        ctx = SecurityContext(granted={"ai.ask"})
        ctx.merge({"memory.read"})
        assert ctx.granted == frozenset({"ai.ask"})

    def test_to_dict(self):
        ctx = SecurityContext(actor="user:alice", granted={"ai.ask"}, metadata={"req_id": "123"})
        d = ctx.to_dict()
        assert d["actor"] == "user:alice"
        assert "ai.ask" in d["granted"]
        assert d["metadata"]["req_id"] == "123"


class TestSecurityContextVar:
    def test_get_returns_none_when_not_set(self):
        assert SecurityContextVar.get() is None

    def test_set_and_get(self):
        ctx = SecurityContext(actor="user:alice", granted={"ai.ask"})
        SecurityContextVar.set(ctx)
        retrieved = SecurityContextVar.get()
        assert retrieved is ctx
        SecurityContextVar.reset()

    def test_reset_clears_context(self):
        ctx = SecurityContext(actor="user:alice")
        SecurityContextVar.set(ctx)
        SecurityContextVar.reset()
        assert SecurityContextVar.get() is None

    def test_thread_isolation(self):
        ctx = SecurityContext(actor="user:alice")
        SecurityContextVar.set(ctx)

        thread_ctx: list = []

        def check():
            thread_ctx.append(SecurityContextVar.get())

        t = threading.Thread(target=check)
        t.start()
        t.join()

        # Thread should not see the main thread's context
        assert thread_ctx[0] is None
        SecurityContextVar.reset()

    def test_propagates_across_async(self):
        import asyncio

        ctx = SecurityContext(actor="user:bob", granted={"ai.ask"})
        SecurityContextVar.set(ctx)

        async def nested():
            return SecurityContextVar.get()

        result = asyncio.run(nested())
        assert result is ctx
        SecurityContextVar.reset()


class TestRequirePermissionDecorator:
    def test_decorator_passes_with_context(self):
        ctx = SecurityContext(granted={"test.op"})
        SecurityContextVar.set(ctx)

        @require_permission("test.op")
        def do_thing():
            return "done"

        assert do_thing() == "done"
        SecurityContextVar.reset()

    def test_decorator_raises_without_context(self):
        SecurityContextVar.reset()

        @require_permission("test.op")
        def do_thing():
            return "done"

        with pytest.raises(PermissionError):
            do_thing()

    def test_decorator_raises_without_permission(self):
        ctx = SecurityContext(granted={"other.op"})
        SecurityContextVar.set(ctx)

        @require_permission("test.op")
        def do_thing():
            return "done"

        with pytest.raises(PermissionError):
            do_thing()
        SecurityContextVar.reset()

    def test_decorator_preserves_args(self):
        ctx = SecurityContext(granted={"test.op"})
        SecurityContextVar.set(ctx)

        @require_permission("test.op")
        def add(a, b):
            return a + b

        assert add(2, 3) == 5
        SecurityContextVar.reset()
