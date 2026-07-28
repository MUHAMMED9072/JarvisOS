from __future__ import annotations

import time

from app.intelligence.context import SessionContext, StageMetrics


class TestSessionContext:
    def test_default_creation(self):
        ctx = SessionContext()
        assert ctx.session_id
        assert ctx.goal == ""
        assert ctx.created_at > 0

    def test_record_stage(self):
        ctx = SessionContext()
        metrics = ctx.record_stage("test_stage", success=True)
        assert metrics.stage_name == "test_stage"
        assert metrics.success is True
        assert len(ctx.stage_metrics) == 1

    def test_complete_stage_updates_end_time(self):
        ctx = SessionContext()
        metrics = ctx.record_stage("slow")
        time.sleep(0.01)
        ctx.complete_stage(metrics)
        assert metrics.end_time > metrics.start_time
        assert metrics.duration_ms > 0

    def test_multiple_stages(self):
        ctx = SessionContext()
        m1 = ctx.record_stage("stage1")
        ctx.complete_stage(m1)
        m2 = ctx.record_stage("stage2")
        ctx.complete_stage(m2)
        assert len(ctx.stage_metrics) == 2

    def test_to_dict(self):
        ctx = SessionContext(session_id="s1", goal="test", goal_type="general")
        ctx.session_data["key"] = "value"
        d = ctx.to_dict()
        assert d["session_id"] == "s1"
        assert d["goal"] == "test"
        assert d["session_data"]["key"] == "value"


class TestStageMetrics:
    def test_defaults(self):
        m = StageMetrics()
        assert m.stage_name == ""
        assert m.success is True

    def test_to_dict(self):
        m = StageMetrics(stage_name="stage", start_time=100.0, end_time=101.0)
        d = m.to_dict()
        assert d["stage_name"] == "stage"
        assert d["duration_ms"] == 1000.0
