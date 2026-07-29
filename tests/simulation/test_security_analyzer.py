import pytest

from app.simulation.security_analyzer import (
    SecurityAnalyzer,
    SecurityImpactReport,
    PermissionAnalysis,
    ExternalConnectionAnalysis,
    FileAccessAnalysis,
    DependencyVulnerability,
    DependencyVulnerabilityCheck,
)
from app.knowledge_graph.store import GraphStore


class TestSecurityAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return SecurityAnalyzer()

    def test_analyze_empty(self, analyzer):
        report = analyzer.analyze("", "EmptyAgent")
        assert report.artifact_name == "EmptyAgent"
        assert report.passed is True
        assert report.overall_score == 0.0

    def test_analyze_excessive_permissions(self, analyzer):
        perms = ["file:read", "shell:execute", "network:listen", "file:write_system"]
        report = analyzer.analyze("class Agent: pass", "PermAgent", permissions=perms)
        assert not report.permission_analysis.justified
        assert report.permission_analysis.score > 0

    def test_analyze_dangerous_permission_combinations(self, analyzer):
        perms = ["file:write", "file:execute"]
        report = analyzer.analyze("", "ComboAgent", permissions=perms)
        assert len(report.permission_analysis.dangerous_combinations) >= 1

    def test_analyze_justified_permissions(self, analyzer):
        perms = ["file:read", "network:connect"]
        report = analyzer.analyze("", "SafeAgent", permissions=perms)
        assert report.permission_analysis.justified

    def test_external_connections(self, analyzer):
        source = '''
import requests
requests.get("https://api.example.com/data")
requests.get("http://insecure.example.org")  # unencrypted
'''
        report = analyzer.analyze(source, "ConnAgent")
        assert len(report.external_connections.domains) >= 2
        assert len(report.external_connections.unencrypted) >= 1

    def test_external_connections_score(self, analyzer):
        source = 'requests.get("http://bad.com")'
        report = analyzer.analyze(source)
        assert report.external_connections.score > 0

    def test_file_access_sensitive(self, analyzer):
        source = '''
with open("/etc/passwd", "r") as f:
    data = f.read()
'''
        report = analyzer.analyze(source)
        assert len(report.file_access.sensitive_files) >= 1
        assert report.file_access.score > 0

    def test_file_access_write(self, analyzer):
        source = '''
with open("/tmp/output.txt", "w") as f:
    f.write("data")
'''
        report = analyzer.analyze(source)
        assert len(report.file_access.write_access) >= 1

    def test_dependency_vulnerabilities(self, analyzer):
        deps = ["requests", "flask"]
        report = analyzer.analyze("", "VulnAgent", dependencies=deps)
        assert len(report.dependency_vulnerabilities.vulnerabilities) >= 1

    def test_dependency_no_vulnerabilities(self, analyzer):
        deps = ["unknown-safe-lib@1.0"]
        report = analyzer.analyze("", "SafeAgent", dependencies=deps)
        assert len(report.dependency_vulnerabilities.vulnerabilities) == 0

    def test_overall_score_high_permissions(self, analyzer):
        perms = ["shell:execute", "network:listen", "file:write_system", "process:spawn"]
        report = analyzer.analyze("", "BadAgent", permissions=perms)
        assert report.overall_score >= 0.3

    def test_overall_score_low(self, analyzer):
        report = analyzer.analyze("", "GoodAgent")
        assert report.overall_score == 0.0

    def test_ip_address_detection(self, analyzer):
        source = 'conn = urlopen("http://192.168.1.1:8080/api")'
        report = analyzer.analyze(source)
        assert len(report.external_connections.ip_addresses) >= 1

    def test_multiple_connections_dedup(self, analyzer):
        source = '''
urlopen("https://example.com/a")
urlopen("https://example.com/b")
'''
        report = analyzer.analyze(source)
        assert len(report.external_connections.domains) == 1

    def test_add_vulnerability(self, analyzer):
        analyzer.add_vulnerability("mylib<2.0", "CVE-2024-0001", "Test vulnerability")
        report = analyzer.analyze("", dependencies=["mylib"])
        assert any("mylib" in v.dependency for v in report.dependency_vulnerabilities.vulnerabilities)

    def test_permission_analysis_to_dict(self):
        pa = PermissionAnalysis(
            requested_permissions=["file:read"],
            excessive_permissions=[],
            dangerous_combinations=[],
            justified=True,
            score=0.0,
        )
        d = pa.to_dict()
        assert d["justified"] is True

    def test_external_connection_to_dict(self):
        ea = ExternalConnectionAnalysis(
            domains=["example.com"],
            ip_addresses=["10.0.0.1"],
            unencrypted=["http://example.com"],
            score=0.3,
        )
        d = ea.to_dict()
        assert d["score"] == 0.3

    def test_file_access_to_dict(self):
        fa = FileAccessAnalysis(
            files_accessed=["/etc/passwd"],
            sensitive_files=["/etc/passwd"],
            write_access=[],
            score=0.5,
        )
        d = fa.to_dict()
        assert len(d["sensitive_files"]) == 1

    def test_dependency_vulnerability_to_dict(self):
        dv = DependencyVulnerability(dependency="requests", cve="CVE-123", description="Test", severity="high")
        d = dv.to_dict()
        assert d["cve"] == "CVE-123"

    def test_dependency_vulnerability_check_to_dict(self):
        dvc = DependencyVulnerabilityCheck(
            vulnerabilities=[DependencyVulnerability(dependency="lib", cve="CVE-1")],
            score=0.2,
        )
        d = dvc.to_dict()
        assert d["score"] == 0.2

    def test_report_to_dict(self):
        report = SecurityImpactReport(
            artifact_name="Test", artifact_type="agent",
            overall_score=0.5, passed=True,
        )
        d = report.to_dict()
        assert d["artifact_name"] == "Test"
        assert d["passed"] is True

    def test_health(self, analyzer):
        h = analyzer.health()
        assert h["alive"] is True
