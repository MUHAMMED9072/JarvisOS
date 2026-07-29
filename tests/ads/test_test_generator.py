import pytest

from app.ads.architecture_designer import ArchitectureSpec
from app.ads.test_generator import TestGenerator, GeneratedTests


def _make_spec(name: str, atype: str = "Agent") -> ArchitectureSpec:
    return ArchitectureSpec(
        name=name,
        artifact_type=atype,
        description=f"A {atype} called {name}",
        components=[],
        interfaces=[],
        data_flow=[],
    )


class TestTestGenerator:
    @pytest.fixture
    def generator(self):
        return TestGenerator()

    def test_generates_unit_tests(self, generator):
        spec = _make_spec("DataMonitor")
        result = generator.generate(spec)
        assert len(result.unit_tests) == 1
        filename = list(result.unit_tests.keys())[0]
        assert "unit" in filename
        assert "DataMonitor" in result.unit_tests[filename]

    def test_generates_integration_tests(self, generator):
        spec = _make_spec("WebScraper")
        result = generator.generate(spec)
        assert len(result.integration_tests) == 1
        filename = list(result.integration_tests.keys())[0]
        assert "integration" in filename

    def test_generates_validation_tests(self, generator):
        spec = _make_spec("MyAgent")
        result = generator.generate(spec)
        assert len(result.validation_tests) == 1
        filename = list(result.validation_tests.keys())[0]
        assert "validation" in filename

    def test_all_tests_use_pytest(self, generator):
        spec = _make_spec("TestAgent")
        result = generator.generate(spec)
        for fname, code in result.unit_tests.items():
            assert "import pytest" in code
        for fname, code in result.integration_tests.items():
            assert "import pytest" in code
        for fname, code in result.validation_tests.items():
            assert "import pytest" in code

    def test_estimate_coverage(self, generator):
        spec = _make_spec("CoverageAgent")
        result = generator.generate(spec)
        coverage = generator.estimate_coverage(result)
        assert 0.0 < coverage <= 1.0

    def test_default_coverage_threshold(self, generator):
        assert generator._coverage_threshold == 0.8

    def test_custom_coverage_threshold(self):
        g = TestGenerator(coverage_threshold=0.9)
        assert g._coverage_threshold == 0.9

    def test_generated_tests_to_dict(self, generator):
        spec = _make_spec("DictTest")
        result = generator.generate(spec)
        d = result.to_dict()
        assert "unit_tests" in d
        assert "coverage_threshold" in d

    def test_health(self, generator):
        h = generator.health()
        assert h["alive"] is True
