from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.memory.context import ContextManager

_DATA_DIR = Path("data") / "memory"


@pytest.fixture
def ctx():
    name = f"test_ctx_{uuid.uuid4().hex}.json"
    c = ContextManager(filename=name)
    yield c
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()


class TestContextManager:
    def test_default_intent_is_none(self, ctx):
        assert ctx.get_intent() is None

    def test_set_and_get_intent(self, ctx):
        ctx.set_intent("greeting")
        assert ctx.get_intent() == "greeting"

    def test_default_skill_is_none(self, ctx):
        assert ctx.get_skill() is None

    def test_set_and_get_skill(self, ctx):
        ctx.set_skill("memory")
        assert ctx.get_skill() == "memory"

    def test_default_entities(self, ctx):
        assert ctx.get_entities() == {}

    def test_set_and_get_entities(self, ctx):
        ctx.set_entities({"app": "chrome"})
        assert ctx.get_entities() == {"app": "chrome"}

    def test_get_entities_is_copy(self, ctx):
        ctx.set_entities({"a": 1})
        entities = ctx.get_entities()
        entities["a"] = 99
        assert ctx.get_entities()["a"] == 1

    def test_track_application(self, ctx):
        ctx.track_application("chrome")
        recent = ctx.get_recent_applications()
        assert "chrome" in recent

    def test_recent_applications_limit(self, ctx):
        for i in range(10):
            ctx.track_application(f"app{i}")
        recent = ctx.get_recent_applications(limit=3)
        assert len(recent) == 3

    def test_recent_applications_order(self, ctx):
        ctx.track_application("first")
        ctx.track_application("second")
        recent = ctx.get_recent_applications(limit=5)
        assert recent[-1] == "second"

    def test_add_and_get_tasks(self, ctx):
        ctx.add_task("task1")
        ctx.add_task("task2")
        tasks = ctx.get_active_tasks()
        assert "task1" in tasks
        assert "task2" in tasks

    def test_remove_task(self, ctx):
        ctx.add_task("task1")
        assert ctx.remove_task("task1") is True
        assert "task1" not in ctx.get_active_tasks()

    def test_remove_task_not_found(self, ctx):
        assert ctx.remove_task("nonexistent") is False

    def test_add_duplicate_task(self, ctx):
        ctx.add_task("task1")
        ctx.add_task("task1")
        tasks = ctx.get_active_tasks()
        assert tasks.count("task1") == 1

    def test_get_history(self, ctx):
        ctx.set_intent("hello")
        ctx.set_skill("test")
        history = ctx.get_history()
        assert len(history) == 2
        assert history[0]["key"] == "intent"
        assert history[1]["key"] == "skill"

    def test_get_history_limit(self, ctx):
        for i in range(20):
            ctx.set_intent(f"intent{i}")
        history = ctx.get_history(limit=5)
        assert len(history) == 5

    def test_clear(self, ctx):
        ctx.set_intent("hello")
        ctx.set_skill("test")
        ctx.clear()
        assert ctx.get_intent() is None
        assert ctx.get_skill() is None
        assert ctx.get_entities() == {}
        assert ctx.get_active_tasks() == []

    def test_persistence(self, ctx):
        ctx.set_intent("hello")
        ctx.set_skill("world")
        ctx2 = ContextManager(filename=ctx.path.name)
        assert ctx2.get_intent() == "hello"
        assert ctx2.get_skill() == "world"
