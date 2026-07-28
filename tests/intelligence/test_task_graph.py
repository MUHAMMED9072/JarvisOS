from __future__ import annotations

import pytest

from app.intelligence.task_graph import (
    Task,
    TaskGraph,
    TaskStatus,
    TaskPriority,
    ResourceEstimate,
)


class TestResourceEstimate:
    def test_defaults(self):
        e = ResourceEstimate()
        assert e.compute == 0.0

    def test_to_dict(self):
        e = ResourceEstimate(compute=0.5, memory_mb=256, time_seconds=30)
        d = e.to_dict()
        assert d["compute"] == 0.5
        assert d["time_seconds"] == 30


class TestTask:
    def test_default_id(self):
        t = Task()
        assert len(t.id) == 16

    def test_default_status(self):
        t = Task()
        assert t.status == TaskStatus.PENDING

    def test_to_dict(self):
        t = Task(name="test-task", description="A test",
                 priority=TaskPriority.HIGH,
                 depends_on=["dep1"],
                 resource_estimate=ResourceEstimate(compute=0.3))
        d = t.to_dict()
        assert d["name"] == "test-task"
        assert d["priority"] == "HIGH"
        assert d["depends_on"] == ["dep1"]
        assert d["resource_estimate"]["compute"] == 0.3


class TestTaskGraph:
    def test_empty_graph(self):
        g = TaskGraph()
        assert g.count() == 0
        assert g.topological_sort() == []

    def test_add_and_get_task(self):
        g = TaskGraph()
        t = Task(name="t1")
        tid = g.add_task(t)
        assert g.get_task(tid) is t

    def test_get_missing_task(self):
        g = TaskGraph()
        assert g.get_task("nonexistent") is None

    def test_remove_task(self):
        g = TaskGraph()
        tid = g.add_task(Task(name="t1"))
        assert g.remove_task(tid)
        assert g.get_task(tid) is None

    def test_remove_missing(self):
        g = TaskGraph()
        assert not g.remove_task("nonexistent")

    def test_list_tasks(self):
        g = TaskGraph()
        g.add_task(Task(name="t1"))
        g.add_task(Task(name="t2"))
        assert len(g.list_tasks()) == 2

    def test_list_tasks_filter_status(self):
        g = TaskGraph()
        t1 = Task(name="t1", status=TaskStatus.PENDING)
        t2 = Task(name="t2", status=TaskStatus.COMPLETED)
        g.add_task(t1)
        g.add_task(t2)
        assert len(g.list_tasks(status=TaskStatus.PENDING)) == 1

    def test_clear(self):
        g = TaskGraph()
        g.add_task(Task(name="t1"))
        g.clear()
        assert g.count() == 0

    def test_update_task_status(self):
        g = TaskGraph()
        tid = g.add_task(Task(name="t1"))
        assert g.update_task_status(tid, TaskStatus.RUNNING)
        assert g.get_task(tid).status == TaskStatus.RUNNING
        assert g.get_task(tid).started_at is not None

    def test_update_task_status_missing(self):
        g = TaskGraph()
        assert not g.update_task_status("nonexistent", TaskStatus.RUNNING)

    def test_update_task_status_completed(self):
        g = TaskGraph()
        tid = g.add_task(Task(name="t1"))
        g.update_task_status(tid, TaskStatus.COMPLETED)
        assert g.get_task(tid).completed_at is not None

    def test_topological_sort_no_deps(self):
        g = TaskGraph()
        g.add_task(Task(name="a"))
        g.add_task(Task(name="b"))
        levels = g.topological_sort()
        assert len(levels) == 1
        assert len(levels[0]) == 2

    def test_topological_sort_linear(self):
        g = TaskGraph()
        a = Task(name="a")
        b = Task(name="b", depends_on=[a.id])
        c = Task(name="c", depends_on=[b.id])
        g.add_task(a)
        g.add_task(b)
        g.add_task(c)
        levels = g.topological_sort()
        assert len(levels) == 3
        assert levels[0] == [a.id]
        assert levels[1] == [b.id]
        assert levels[2] == [c.id]

    def test_topological_sort_diamond(self):
        g = TaskGraph()
        a = Task(name="a")
        b = Task(name="b", depends_on=[a.id])
        c = Task(name="c", depends_on=[a.id])
        d = Task(name="d", depends_on=[b.id, c.id])
        g.add_task(a)
        g.add_task(b)
        g.add_task(c)
        g.add_task(d)
        levels = g.topological_sort()
        assert len(levels) == 3
        assert levels[0] == [a.id]
        assert b.id in levels[1] and c.id in levels[1]
        assert levels[2] == [d.id]

    def test_find_parallelizable(self):
        g = TaskGraph()
        a = Task(name="a")
        b = Task(name="b", depends_on=["a"])
        c = Task(name="c", depends_on=["a"])
        d = Task(name="d", depends_on=["a"])
        g.add_task(a)
        g.add_task(b)
        g.add_task(c)
        g.add_task(d)
        parallel = g.find_parallelizable()
        assert len(parallel) >= 1
        assert len(parallel[0]) >= 3

    def test_critical_path_single(self):
        g = TaskGraph()
        t = Task(name="only", resource_estimate=ResourceEstimate(time_seconds=5))
        g.add_task(t)
        path = g.critical_path()
        assert path == [t.id]

    def test_critical_path_diamond(self):
        g = TaskGraph()
        a = Task(name="a", resource_estimate=ResourceEstimate(time_seconds=1))
        b = Task(name="b", depends_on=[a.id], resource_estimate=ResourceEstimate(time_seconds=5))
        c = Task(name="c", depends_on=[a.id], resource_estimate=ResourceEstimate(time_seconds=2))
        d = Task(name="d", depends_on=[b.id, c.id], resource_estimate=ResourceEstimate(time_seconds=1))
        g.add_task(a)
        g.add_task(b)
        g.add_task(c)
        g.add_task(d)
        path = g.critical_path()
        # b is longer than c, so path should be a -> b -> d
        assert path[0] == a.id
        assert path[-1] == d.id
        assert b.id in path

    def test_critical_path_duration(self):
        g = TaskGraph()
        a = Task(name="a", resource_estimate=ResourceEstimate(time_seconds=2))
        b = Task(name="b", depends_on=[a.id], resource_estimate=ResourceEstimate(time_seconds=3))
        g.add_task(a)
        g.add_task(b)
        assert g.critical_path_duration() == 5.0

    def test_critical_path_empty_graph(self):
        g = TaskGraph()
        assert g.critical_path_duration() == 0.0

    def test_to_text_empty(self):
        g = TaskGraph()
        text = g.to_text()
        assert "empty" in text

    def test_to_text_with_tasks(self):
        g = TaskGraph()
        g.add_task(Task(name="task1", resource_estimate=ResourceEstimate(time_seconds=10)))
        text = g.to_text()
        assert "Task Graph" in text
        assert "task1" in text

    def test_to_dict_roundtrip(self):
        g = TaskGraph()
        t = Task(name="test", description="desc", resource_estimate=ResourceEstimate(time_seconds=5))
        g.add_task(t)
        data = g.to_dict()
        assert "tasks" in data
        assert "levels" in data
        assert "critical_path" in data
        restored = TaskGraph.from_dict(data)
        assert restored.count() == 1
        restored_task = restored.get_task(t.id)
        assert restored_task is not None
        assert restored_task.name == "test"
        assert restored_task.resource_estimate.time_seconds == 5

    def test_from_dict_preserves_status(self):
        g = TaskGraph()
        t = Task(name="test", status=TaskStatus.COMPLETED)
        g.add_task(t)
        data = g.to_dict()
        restored = TaskGraph.from_dict(data)
        assert restored.get_task(t.id).status == TaskStatus.COMPLETED

    def test_thread_safe(self):
        import threading
        g = TaskGraph()
        errors = []

        def work():
            try:
                for i in range(50):
                    g.add_task(Task(name=f"t{i}"))
                    g.topological_sort()
                    g.critical_path()
                    g.to_text()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=work) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert g.count() == 200
