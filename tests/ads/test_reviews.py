import pytest

from app.ads.benchmark import BenchmarkRunner
from app.ads.security_review import SecurityReviewer
from app.ads.performance_review import PerformanceReviewer


# ── Benchmark Tests ─────────────────────────────────────────────────

class TestBenchmarkRunner:
    @pytest.fixture
    def runner(self):
        return BenchmarkRunner()

    def test_benchmark_simple_code(self, runner):
        report = runner.benchmark('print("hello")', artifact_name="test_artifact")
        assert report.artifact_name == "test_artifact"
        assert report.measured_latency_ms > 0
        assert report.passed is True

    def test_benchmark_report_fields(self, runner):
        report = runner.benchmark('x = 1 + 1', artifact_name="calc")
        d = report.to_dict()
        assert d["artifact_name"] == "calc"
        assert "latency_change_pct" in d

    def test_health(self, runner):
        h = runner.health()
        assert h["alive"] is True


# ── Security Review Tests ───────────────────────────────────────────

SAFE_CODE = '''
def hello():
    return "world"
'''

DANGEROUS_CODE = '''
def process(data):
    result = eval(data)
    return result
'''

MIXED_CODE = '''
import pickle
def load_data(path):
    with open(path, "rb") as f:
        return pickle.load(f)
'''


class TestSecurityReviewer:
    @pytest.fixture
    def reviewer(self):
        return SecurityReviewer()

    def test_safe_code(self, reviewer):
        report = reviewer.review(SAFE_CODE, "safe_artifact")
        assert report.passed is True
        assert len(report.issues) == 0

    def test_dangerous_code(self, reviewer):
        report = reviewer.review(DANGEROUS_CODE, "dangerous")
        assert report.passed is False
        assert any(i.pattern_name == "eval_usage" for i in report.issues)

    def test_mixed_code(self, reviewer):
        report = reviewer.review(MIXED_CODE, "mixed")
        assert any(i.pattern_name == "pickle_load" for i in report.issues)

    def test_high_severity_count(self, reviewer):
        code = '''
x = eval("1+1")
y = exec("z = 2")
'''
        report = reviewer.review(code)
        assert report.high_count >= 2

    def test_report_to_dict(self, reviewer):
        report = reviewer.review(SAFE_CODE, "test")
        d = report.to_dict()
        assert d["artifact_name"] == "test"
        assert "total_issues" in d

    def test_syntax_error_detection(self, reviewer):
        report = reviewer.review('print(')  # syntax error
        assert any(i.pattern_name == "syntax_error" for i in report.issues)

    def test_health(self, reviewer):
        h = reviewer.health()
        assert h["alive"] is True
        assert h["dangerous_patterns"] >= 10


# ── Performance Review Tests ────────────────────────────────────────

PERF_CODE = '''
for i in range(10):
    for j in range(10):
        for k in range(10):
            for m in range(10):
                result = list(range(10))

import requests
import os
import sys
import json
import math

def recursive(n):
    if n <= 1:
        return n
    return recursive(n - 1) + recursive(n - 2)
'''


class TestPerformanceReviewer:
    @pytest.fixture
    def reviewer(self):
        return PerformanceReviewer()

    def test_small_code_has_few_issues(self, reviewer):
        report = reviewer.review('print("hello")', "simple")
        assert len(report.issues) == 0

    def test_complex_code_identifies_issues(self, reviewer):
        report = reviewer.review(PERF_CODE, "complex")
        assert len(report.issues) >= 1

    def test_hotspots_identified(self, reviewer):
        report = reviewer.review(PERF_CODE)
        assert len(report.hotspots) >= 1

    def test_resource_score(self, reviewer):
        report = reviewer.review(PERF_CODE)
        assert 0.0 <= report.resource_score <= 1.0

    def test_report_to_dict(self, reviewer):
        report = reviewer.review(PERF_CODE, "test")
        d = report.to_dict()
        assert d["artifact_name"] == "test"
        assert "resource_score" in d

    def test_health(self, reviewer):
        h = reviewer.health()
        assert h["alive"] is True
