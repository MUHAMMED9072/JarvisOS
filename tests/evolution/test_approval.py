"""Tests for Evolution Engine approval policies."""

from __future__ import annotations

from typing import Any

import pytest

from app.evolution.approval import (
    ApprovalDecision,
    ApprovalPolicy,
    InteractiveCliApprovalPolicy,
)
from app.evolution.installer import ApprovalRequest


def _request(summary: dict[str, Any] | None = None) -> ApprovalRequest:
    return ApprovalRequest(
        patch_path="data/generated_patch.py",
        target_path="app/skills/loader.py",
        backup_path="data/evolution/backups/loader.py-20240101",
        summary=summary or {"validation_ok": True, "test_success": True},
    )


class TestApprovalPolicyAbstract:
    def test_approval_policy_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            ApprovalPolicy()  # type: ignore[abstract]


class TestInteractiveCliApprovalPolicy:
    def test_y_approves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")

        decision = InteractiveCliApprovalPolicy().request(_request())

        assert decision.approved is True
        assert decision.approver == "cli"
        assert decision.timestamp  # ISO-8601
        assert decision.reason == ""

    def test_yes_approves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "yes")

        decision = InteractiveCliApprovalPolicy().request(_request())

        assert decision.approved is True
        assert decision.reason == ""

    def test_uppercase_y_approves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "Y")

        assert InteractiveCliApprovalPolicy().request(_request()).approved is True

    @pytest.mark.parametrize("response", ["n", "no", "", "garbage", "maybe"])
    def test_default_no_for_anything_else(
        self,
        monkeypatch: pytest.MonkeyPatch,
        response: str,
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: response)

        decision = InteractiveCliApprovalPolicy().request(_request())

        assert decision.approved is False
        assert decision.approver == "cli"
        assert decision.reason == "user denied at prompt"

    def test_eof_denies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise_eof(*_a: Any, **_k: Any) -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", _raise_eof)

        decision = InteractiveCliApprovalPolicy().request(_request())

        assert decision.approved is False
        assert decision.reason == "interrupted before answer"

    def test_keyboard_interrupt_denies(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _raise_kbi(*_a: Any, **_k: Any) -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", _raise_kbi)

        decision = InteractiveCliApprovalPolicy().request(_request())

        assert decision.approved is False
        assert decision.reason == "interrupted before answer"

    def test_summary_is_printed_before_prompt(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        captured: list[str] = []
        monkeypatch.setattr(
            "builtins.input", lambda *_a, **_k: captured.append("y") or "n",
        )

        InteractiveCliApprovalPolicy().request(
            _request({"validation_ok": True, "sandbox_success": False}),
        )
        # input() writes its prompt to stderr; capture both streams.
        captured_io = capsys.readouterr()
        combined = captured_io.out + captured_io.err

        assert "PENDING INSTALL" in combined
        assert "app/skills/loader.py" in combined
        assert "data/generated_patch.py" in combined
        assert "data/evolution/backups/loader.py-20240101" in combined
        assert "validation_ok" in combined
        assert "sandbox_success" in combined
        assert "Approve installation? (y/N): " in combined
        assert captured == ["y"]

    def test_decision_fields_match_dataclass_shape(self) -> None:
        decision = ApprovalDecision(
            approved=True,
            approver="cli",
            timestamp="2024-01-15T12:34:56+00:00",
            reason="",
        )
        assert decision.approved is True
        assert decision.reason == ""
