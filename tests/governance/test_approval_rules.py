from __future__ import annotations

import pytest

from app.governance.approval_rules import (
    ApprovalManager,
    ApprovalRule,
    ApprovalRequest,
    ApprovalOutcome,
)


class TestApprovalRule:
    def test_defaults(self):
        r = ApprovalRule(name="test")
        assert r.min_approvers == 1
        assert r.min_trust_level == "medium"
        assert r.timeout_seconds == 3600.0
        assert not r.auto_approve

    def test_to_dict(self):
        r = ApprovalRule(name="test", min_approvers=2)
        d = r.to_dict()
        assert d["name"] == "test"
        assert d["min_approvers"] == 2


class TestApprovalRequest:
    def test_defaults(self):
        req = ApprovalRequest()
        assert req.outcome == ApprovalOutcome.PENDING
        assert req.approved_count == 0
        assert req.rejected_count == 0
        assert not req.is_expired

    def test_to_dict(self):
        req = ApprovalRequest(
            rule_id="r1",
            artifact_id="art1",
            requester="user1",
            reason="need access",
        )
        d = req.to_dict()
        assert d["rule_id"] == "r1"
        assert d["outcome"] == "pending"
        assert d["requester"] == "user1"


class TestApprovalManager:
    def test_register_and_get_rule(self):
        mgr = ApprovalManager()
        r = ApprovalRule(name="r1", min_approvers=1)
        rid = mgr.register_rule(r)
        assert mgr.get_rule(rid) is r

    def test_get_rule_missing(self):
        mgr = ApprovalManager()
        assert mgr.get_rule("missing") is None

    def test_delete_rule(self):
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1"))
        assert mgr.delete_rule(rid)
        assert mgr.get_rule(rid) is None

    def test_delete_rule_missing(self):
        mgr = ApprovalManager()
        assert not mgr.delete_rule("missing")

    def test_list_rules(self):
        mgr = ApprovalManager()
        mgr.register_rule(ApprovalRule(name="r1"))
        mgr.register_rule(ApprovalRule(name="r2"))
        assert len(mgr.list_rules()) == 2

    def test_create_request(self):
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1", min_approvers=1))
        req = mgr.create_request(rid, "art1", "user1", "need access")
        assert req.rule_id == rid
        assert req.artifact_id == "art1"
        assert req.requester == "user1"
        assert req.outcome == ApprovalOutcome.PENDING

    def test_create_request_unknown_rule(self):
        mgr = ApprovalManager()
        with pytest.raises(ValueError, match="not found"):
            mgr.create_request("missing", "art1", "user1")

    def test_approve(self):
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1", min_approvers=1))
        req = mgr.create_request(rid, "art1", "user1")
        outcome = mgr.approve(req.id, "approver1")
        assert outcome == ApprovalOutcome.APPROVED
        req2 = mgr.get_request(req.id)
        assert req2.outcome == ApprovalOutcome.APPROVED

    def test_reject(self):
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1", min_approvers=1))
        req = mgr.create_request(rid, "art1", "user1")
        outcome = mgr.reject(req.id, "approver1")
        assert outcome == ApprovalOutcome.REJECTED
        req2 = mgr.get_request(req.id)
        assert req2.outcome == ApprovalOutcome.REJECTED

    def test_approve_missing_request(self):
        mgr = ApprovalManager()
        assert mgr.approve("missing", "approver1") is None

    def test_reject_missing_request(self):
        mgr = ApprovalManager()
        assert mgr.reject("missing", "approver1") is None

    def test_list_requests_filter_outcome(self):
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1", min_approvers=1))
        req1 = mgr.create_request(rid, "art1", "user1")
        req2 = mgr.create_request(rid, "art2", "user1")
        mgr.approve(req1.id, "approver1")
        pending = mgr.list_requests(outcome=ApprovalOutcome.PENDING)
        approved = mgr.list_requests(outcome=ApprovalOutcome.APPROVED)
        assert len(pending) == 1
        assert len(approved) == 1

    def test_list_requests_filter_requester(self):
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1", min_approvers=1))
        mgr.create_request(rid, "art1", "user1")
        mgr.create_request(rid, "art2", "user2")
        assert len(mgr.list_requests(requester="user1")) == 1

    def test_multiple_approvers_needed(self):
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1", min_approvers=2))
        req = mgr.create_request(rid, "art1", "user1")
        outcome1 = mgr.approve(req.id, "approver1")
        assert outcome1 == ApprovalOutcome.PENDING
        outcome2 = mgr.approve(req.id, "approver2")
        assert outcome2 == ApprovalOutcome.APPROVED

    def test_already_decided(self):
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1", min_approvers=1))
        req = mgr.create_request(rid, "art1", "user1")
        mgr.approve(req.id, "approver1")
        outcome = mgr.approve(req.id, "approver2")
        assert outcome == ApprovalOutcome.APPROVED

    def test_thread_safe(self):
        import threading
        mgr = ApprovalManager()
        rid = mgr.register_rule(ApprovalRule(name="r1", min_approvers=5))
        req = mgr.create_request(rid, "art1", "user1")
        errors = []

        def approve():
            try:
                mgr.approve(req.id, f"approver_{threading.get_ident()}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=approve) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        final_req = mgr.get_request(req.id)
        assert final_req.outcome == ApprovalOutcome.APPROVED
        assert final_req.approved_count >= 5
