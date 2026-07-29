import pytest

from app.ads.content_generator import GeneratedContent
from app.ads.learning import FeedbackEntry, Heuristic, LearningLoop, LearningResult
from app.ads.metrics import ArtifactMetrics, MetricsCollector
from app.ads.versioning import ArtifactVersion, VersionManager, VersionResult
from app.knowledge_graph.store import GraphStore


def _make_content(name: str, atype: str = "Agent", caps: list[str] | None = None) -> GeneratedContent:
    return GeneratedContent(
        files={f"{name}.py": f"class {name}: pass"},
        manifest={
            "name": name,
            "version": "1.0.0",
            "type": atype,
            "description": f"A test {atype}",
            "capabilities": caps or [],
        },
        base_path=f"runtime/generated/{name}",
    )


class TestVersionManager:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def vm(self, graph):
        return VersionManager(graph)

    def _register_artifact(self, graph, name: str, atype: str = "agent"):
        return graph.create_entity(
            type=atype,
            name=name,
            properties={"version": "1.0.0", "type": atype},
        )

    def test_create_initial_version(self, vm, graph):
        self._register_artifact(graph, "TestAgent")
        content = _make_content("TestAgent", "Agent", caps=["web"])
        result = vm.create_initial_version("TestAgent", content)
        assert result.success is True
        assert result.version is not None
        assert result.version.version == "1.0.0"
        assert "Initial release" in result.version.changelog[0]

    def test_create_initial_version_unregistered(self, vm, graph):
        content = _make_content("NoEntity", "Agent")
        result = vm.create_initial_version("NoEntity", content)
        assert result.success is False
        assert "not registered" in result.error

    def test_create_initial_version_changelog(self, vm, graph):
        self._register_artifact(graph, "CapAgent")
        content = _make_content("CapAgent", "Agent", caps=["monitor", "alert"])
        result = vm.create_initial_version("CapAgent", content)
        assert result.success is True
        assert any("Capabilities" in c for c in result.version.changelog)

    def test_get_version(self, vm, graph):
        self._register_artifact(graph, "GetAgent")
        content = _make_content("GetAgent")
        vm.create_initial_version("GetAgent", content)
        v = vm.get_version("GetAgent", "1.0.0")
        assert v is not None
        assert v.version == "1.0.0"

    def test_get_version_not_found(self, vm, graph):
        v = vm.get_version("Nonexistent", "1.0.0")
        assert v is None

    def test_get_latest_version(self, vm, graph):
        self._register_artifact(graph, "LatestAgent")
        content = _make_content("LatestAgent")
        vm.create_initial_version("LatestAgent", content)
        latest = vm.get_version("LatestAgent")
        assert latest is not None
        assert latest.version == "1.0.0"

    def test_list_versions(self, vm, graph):
        self._register_artifact(graph, "ListAgent")
        content = _make_content("ListAgent")
        vm.create_initial_version("ListAgent", content)
        versions = vm.list_versions("ListAgent")
        assert len(versions) >= 1

    def test_version_to_dict(self, vm, graph):
        self._register_artifact(graph, "DictAgent")
        content = _make_content("DictAgent")
        result = vm.create_initial_version("DictAgent", content)
        d = result.to_dict()
        assert d["success"] is True

    def test_version_to_dict_no_version(self, vm, graph):
        result = VersionResult(success=False, error="test error")
        d = result.to_dict()
        assert d["success"] is False
        assert d["version"] is None

    def test_health(self, vm):
        h = vm.health()
        assert h["alive"] is True


class TestMetricsCollector:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def mc(self, graph):
        return MetricsCollector(graph)

    def test_initialize_baseline(self, mc, graph):
        result = mc.initialize_baseline("TestAgent", "agent")
        assert result.success is True
        assert result.metrics is not None
        assert result.metrics.artifact_name == "TestAgent"

    def test_initialize_baseline_with_benchmark(self, mc, graph):
        bench = {"avg_latency_ms": 150.0, "peak_memory_mb": 64.0, "execution_count": 1}
        result = mc.initialize_baseline("BenchAgent", "agent", bench)
        assert result.metrics.avg_latency_ms == 150.0
        assert result.metrics.peak_memory_mb == 64.0

    def test_initialize_baseline_persists_to_kg(self, mc, graph):
        mc.initialize_baseline("KGAgent", "agent")
        entities = graph.get_entity_by_name("metrics_KGAgent")
        assert len(entities) >= 1

    def test_record_execution(self, mc, graph):
        mc.initialize_baseline("ExecAgent", "agent")
        result = mc.record_execution("ExecAgent", True, latency_ms=50.0)
        assert result.success is True
        assert result.metrics.execution_count == 1  # baseline 0 + 1 record
        assert result.metrics.avg_latency_ms > 0

    def test_record_execution_no_baseline(self, mc, graph):
        result = mc.record_execution("NoBaseline", False)
        assert result.success is False

    def test_record_failure(self, mc, graph):
        mc.initialize_baseline("FailAgent", "agent")
        result = mc.record_execution("FailAgent", False)
        assert result.metrics.failure_count == 1
        assert result.metrics.success_count == 0

    def test_record_updates_peak_memory(self, mc, graph):
        mc.initialize_baseline("MemAgent", "agent")
        mc.record_execution("MemAgent", True, memory_mb=128.0)
        mc.record_execution("MemAgent", True, memory_mb=256.0)
        metrics = mc.get_metrics("MemAgent")
        assert metrics.peak_memory_mb == 256.0

    def test_get_metrics(self, mc, graph):
        mc.initialize_baseline("GetAgent", "agent")
        metrics = mc.get_metrics("GetAgent")
        assert metrics is not None
        assert metrics.artifact_name == "GetAgent"

    def test_get_metrics_not_found(self, mc, graph):
        metrics = mc.get_metrics("Nonexistent")
        assert metrics is None

    def test_list_metrics(self, mc, graph):
        mc.initialize_baseline("AgentA", "agent")
        mc.initialize_baseline("AgentB", "agent")
        all_m = mc.list_metrics()
        assert len(all_m) >= 2

    def test_success_rate(self, mc, graph):
        mc.initialize_baseline("RateAgent", "agent")
        mc.record_execution("RateAgent", True)
        mc.record_execution("RateAgent", False)
        metrics = mc.get_metrics("RateAgent")
        assert metrics.execution_count == 2  # baseline 0 + 2 records
        assert metrics.success_count == 1
        assert metrics.failure_count == 1

    def test_quality_score_default(self, mc, graph):
        result = mc.initialize_baseline("QAgent", "agent")
        assert result.metrics.quality_score == 1.0

    def test_quality_score_from_benchmark(self, mc, graph):
        bench = {"avg_latency_ms": 600.0, "peak_memory_mb": 300.0}
        result = mc.initialize_baseline("QBench", "agent", bench)
        assert result.metrics.quality_score < 1.0

    def test_health(self, mc):
        h = mc.health()
        assert h["alive"] is True


class TestLearningLoop:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def ll(self, graph):
        return LearningLoop(graph)

    @pytest.fixture
    def feedback(self):
        return FeedbackEntry(
            artifact_name="TestAgent",
            execution_id="exec_001",
            success=True,
            latency_ms=100.0,
            feedback="All good",
        )

    def test_record_feedback(self, ll, feedback):
        result = ll.record_feedback(feedback)
        assert result.success is True
        assert result.feedback.artifact_name == "TestAgent"

    def test_record_failure_feedback(self, ll, graph):
        fb = FeedbackEntry(
            artifact_name="FailAgent",
            execution_id="exec_002",
            success=False,
            latency_ms=2000.0,
            error_type="Timeout",
            feedback="Timed out",
        )
        result = ll.record_feedback(fb)
        assert result.success is True
        assert result.feedback.success is False

    def test_get_feedback(self, ll, feedback):
        ll.record_feedback(feedback)
        fb2 = FeedbackEntry(artifact_name="OtherAgent", execution_id="exec_003", success=True)
        ll.record_feedback(fb2)
        results = ll.get_feedback("TestAgent")
        assert len(results) == 1

    def test_get_all_feedback(self, ll, feedback):
        ll.record_feedback(feedback)
        all_fb = ll.get_all_feedback()
        assert len(all_fb) >= 1

    def test_get_heuristics(self, ll):
        heuristics = ll.get_heuristics()
        assert "latency_penalty" in heuristics
        assert "error_rate_boost" in heuristics
        assert "success_reinforcement" in heuristics

    def test_update_heuristic_weight(self, ll):
        assert ll.update_heuristic_weight("latency_penalty", 0.5) is True
        assert ll.get_heuristic("latency_penalty").weight == 0.5

    def test_update_heuristic_weight_not_found(self, ll):
        assert ll.update_heuristic_weight("nonexistent", 0.5) is False

    def test_heuristic_accuracy_default(self, ll):
        h = ll.get_heuristic("latency_penalty")
        assert h.accuracy == 1.0

    def test_feedback_updates_latency_heuristic(self, ll):
        fb = FeedbackEntry(artifact_name="SlowAgent", latency_ms=600.0, success=True)
        result = ll.record_feedback(fb)
        assert "latency_penalty" in result.heuristics_updated

    def test_feedback_updates_error_rate_heuristic(self, ll):
        fb = FeedbackEntry(artifact_name="ErrAgent", success=False, error_type="Crash")
        result = ll.record_feedback(fb)
        assert "error_rate_boost" in result.heuristics_updated

    def test_feedback_updates_success_reinforcement(self, ll):
        fb = FeedbackEntry(artifact_name="GoodAgent", success=True)
        result = ll.record_feedback(fb)
        assert "success_reinforcement" in result.heuristics_updated

    def test_compute_quality_adjustment_default(self, ll):
        adj = ll.compute_quality_adjustment("UnknownAgent")
        assert adj == 0.0

    def test_compute_quality_adjustment_negative(self, ll):
        for _ in range(10):
            fb = FeedbackEntry(artifact_name="BadAgent", success=False, latency_ms=2000.0)
            ll.record_feedback(fb)
        adj = ll.compute_quality_adjustment("BadAgent")
        assert adj < 0

    def test_compute_quality_adjustment_positive(self, ll):
        for _ in range(10):
            fb = FeedbackEntry(artifact_name="GoodAgent", success=True, latency_ms=10.0)
            ll.record_feedback(fb)
        adj = ll.compute_quality_adjustment("GoodAgent")
        assert adj > 0

    def test_feedback_to_dict(self, ll, feedback):
        d = feedback.to_dict()
        assert d["artifact_name"] == "TestAgent"
        assert d["success"] is True

    def test_heuristic_to_dict(self, ll):
        h = Heuristic(name="test", description="test heuristic", weight=0.7)
        d = h.to_dict()
        assert d["name"] == "test"
        assert d["weight"] == 0.7

    def test_learning_result_to_dict(self, ll, feedback):
        result = ll.record_feedback(feedback)
        d = result.to_dict()
        assert d["success"] is True
        assert d["feedback"]["artifact_name"] == "TestAgent"

    def test_health(self, ll):
        h = ll.health()
        assert h["alive"] is True
        assert h["heuristic_count"] >= 3
