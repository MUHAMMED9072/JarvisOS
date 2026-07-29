from __future__ import annotations

from app.tools.integration.monitor import ToolMonitor, TraceSpan


class TestToolMonitor:
    def test_begin_and_end_trace(self) -> None:
        monitor = ToolMonitor()
        tid = monitor.begin_trace("shell_tool", "1.0.0", "exec")
        monitor.end_trace(tid, True)
        traces = monitor.get_traces()
        assert len(traces) == 1
        assert traces[0].tool_name == "shell_tool"
        assert traces[0].success

    def test_trace_failure(self) -> None:
        monitor = ToolMonitor()
        tid = monitor.begin_trace("fail_tool", "1.0.0", "run")
        monitor.end_trace(tid, False, "something broke")
        traces = monitor.get_traces()
        assert not traces[0].success
        assert traces[0].error_message == "something broke"

    def test_add_span(self) -> None:
        monitor = ToolMonitor()
        tid = monitor.begin_trace("test_tool", "1.0.0", "analyze")
        span = TraceSpan(name="validation", start_time=100.0, end_time=101.0, status="ok")
        assert monitor.add_span(tid, span)
        traces = monitor.get_traces()
        assert len(traces[0].spans) == 1
        assert traces[0].spans[0].name == "validation"

    def test_add_span_nonexistent_trace(self) -> None:
        monitor = ToolMonitor()
        span = TraceSpan(name="test")
        assert not monitor.add_span("no-such-trace", span)

    def test_get_traces_by_tool(self) -> None:
        monitor = ToolMonitor()
        t1 = monitor.begin_trace("tool_a", "1.0.0", "exec")
        monitor.end_trace(t1, True)
        t2 = monitor.begin_trace("tool_b", "2.0.0", "exec")
        monitor.end_trace(t2, True)
        traces = monitor.get_traces(tool_name="tool_a")
        assert len(traces) == 1
        assert traces[0].tool_name == "tool_a"

    def test_get_traces_limit(self) -> None:
        monitor = ToolMonitor()
        for i in range(10):
            t = monitor.begin_trace(f"t{i}", "1.0.0", "exec")
            monitor.end_trace(t, True)
        traces = monitor.get_traces(limit=3)
        assert len(traces) == 3

    def test_metrics_after_execution(self) -> None:
        monitor = ToolMonitor()
        t1 = monitor.begin_trace("shell_tool", "1.0.0", "exec")
        monitor.end_trace(t1, True)
        t2 = monitor.begin_trace("shell_tool", "1.0.0", "exec")
        monitor.end_trace(t2, False, "err")
        metrics = monitor.get_metrics()
        key = "shell_tool:exec"
        assert key in metrics
        assert metrics[key]["count"] == 2
        assert metrics[key]["errors"] == 1

    def test_health(self) -> None:
        monitor = ToolMonitor()
        h = monitor.health()
        assert h["alive"]

    def test_max_traces_buffer(self) -> None:
        monitor = ToolMonitor(max_traces=3)
        for i in range(5):
            t = monitor.begin_trace(f"t{i}", "1.0.0", "exec")
            monitor.end_trace(t, True)
        assert len(monitor.get_traces()) == 3

    def test_trace_duration(self) -> None:
        monitor = ToolMonitor()
        tid = monitor.begin_trace("test", "1.0.0", "exec")
        monitor.end_trace(tid, True)
        traces = monitor.get_traces()
        assert traces[0].total_duration_ms >= 0
