import pytest

from app.ads.approval import ApprovalDecision, ApprovalGate
from app.ads.benchmark import BenchmarkReport
from app.ads.governance import GovernanceChecker, GovernanceResult
from app.ads.performance_review import PerformanceReport
from app.ads.security_review import SecurityReport


class TestGovernanceChecker:
    @pytest.fixture
    def checker(self):
        return GovernanceChecker()

    def test_low_risk_auto_approve(self, checker):
        result = checker.check("safe_agent", trust_level="high")
        assert result.passed is True
        assert result.approval_mode == "auto-approve"
        assert result.risk_score == 0

    def test_high_risk_rejected(self, checker):
        sec = SecurityReport(artifact_name="bad", high_count=3, passed=False)
        result = checker.check("bad_agent", trust_level="low", security_report=sec)
        assert result.passed is False
        assert result.approval_mode == "rejected"

    def test_medium_risk_manual(self, checker):
        # 4 medium issues (passed=False so risk is counted)
        sec = SecurityReport(artifact_name="med", medium_count=4, passed=False)
        result = checker.check("med_agent", trust_level="low", security_report=sec)
        assert result.approval_mode == "manual"

    def test_security_failure_adds_violations(self, checker):
        sec = SecurityReport(artifact_name="s", high_count=1, passed=False)
        result = checker.check("s", trust_level="low", security_report=sec)
        assert len(result.policy_violations) >= 1

    def test_governance_result_to_dict(self, checker):
        result = GovernanceResult(artifact_name="t", risk_score=5.0)
        d = result.to_dict()
        assert d["artifact_name"] == "t"
        assert "approval_mode" in d

    def test_health(self, checker):
        h = checker.health()
        assert h["alive"] is True


class TestApprovalGate:
    @pytest.fixture
    def gate(self):
        return ApprovalGate(timeout_seconds=0.1)

    def test_auto_approve(self, gate):
        gov = GovernanceResult(artifact_name="a", approval_mode="auto-approve", passed=True)
        req = gate.submit("a", gov)
        assert req.decision == ApprovalDecision.APPROVED

    def test_auto_reject(self, gate):
        gov = GovernanceResult(artifact_name="b", approval_mode="rejected", passed=False)
        req = gate.submit("b", gov)
        assert req.decision == ApprovalDecision.REJECTED

    def test_manual_pending(self, gate):
        gov = GovernanceResult(artifact_name="c", approval_mode="manual", passed=True)
        req = gate.submit("c", gov)
        assert req.decision == ApprovalDecision.PENDING

    def test_manual_approve(self, gate):
        gov = GovernanceResult(artifact_name="d", approval_mode="manual", passed=True)
        gate.submit("d", gov)
        req = gate.approve("d", reviewer="admin")
        assert req is not None
        assert req.decision == ApprovalDecision.APPROVED

    def test_manual_reject(self, gate):
        gov = GovernanceResult(artifact_name="e", approval_mode="manual", passed=True)
        gate.submit("e", gov)
        req = gate.reject("e", reviewer="admin")
        assert req is not None
        assert req.decision == ApprovalDecision.REJECTED

    def test_timeout_default_reject(self, gate):
        gov = GovernanceResult(artifact_name="f", approval_mode="manual", passed=True)
        gate.submit("f", gov)
        import time
        time.sleep(0.15)
        req = gate.check_timeout("f")
        assert req is not None
        assert req.decision == ApprovalDecision.TIMEOUT

    def test_timeout_approve_mode(self):
        gate = ApprovalGate(timeout_seconds=0.1, on_timeout="approve")
        gov = GovernanceResult(artifact_name="g", approval_mode="manual", passed=True)
        gate.submit("g", gov)
        import time
        time.sleep(0.15)
        req = gate.check_timeout("g")
        assert req is not None
        assert req.decision == ApprovalDecision.APPROVED

    def test_get_status(self, gate):
        gov = GovernanceResult(artifact_name="h", approval_mode="auto-approve", passed=True)
        gate.submit("h", gov)
        req = gate.get_status("h")
        assert req is not None
        assert req.artifact_name == "h"

    def test_get_status_nonexistent(self, gate):
        assert gate.get_status("nonexistent") is None

    def test_list_pending(self, gate):
        gov = GovernanceResult(artifact_name="i", approval_mode="manual", passed=True)
        gate.submit("i", gov)
        gate.submit("j", GovernanceResult(artifact_name="j", approval_mode="auto-approve", passed=True))
        pending = gate.list_pending()
        assert len(pending) == 1

    def test_health(self, gate):
        h = gate.health()
        assert h["alive"] is True

    def test_approval_request_to_dict(self, gate):
        gov = GovernanceResult(artifact_name="k", approval_mode="auto-approve", passed=True)
        req = gate.submit("k", gov)
        d = req.to_dict()
        assert d["artifact_name"] == "k"
