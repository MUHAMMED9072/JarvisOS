"""Tests for P9-05: Evolution Engine AI Integration.

Verifies that all AI interactions in the Evolution Engine flow through
EvolutionAI -> AIRouter (capability-routed) instead of direct AIManager
construction with hardcoded provider names.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

from app.ai.providers.base import AIResponse, ProviderCapability
from app.core.registry import ServiceRegistry
from app.evolution.ai import EvolutionAI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ai_response(text: str = "mock response", **kw: object) -> AIResponse:
    return AIResponse(
        text,
        provider=kw.get("provider", "test"),
        model=kw.get("model", "mock"),
        latency_ms=kw.get("latency_ms", 10.0),
        metadata=kw.get("metadata", {}),
    )


def _make_registry(
    *,
    ai_response: AIResponse | None = None,
    plan_result: object | None = None,
) -> ServiceRegistry:
    registry = ServiceRegistry()

    router = MagicMock()
    if ai_response is not None:
        router.ask_routed.return_value = ai_response
    else:
        router.ask_routed.return_value = _make_ai_response()
    registry.register("ai_router", router)

    ai_manager = MagicMock()
    if plan_result is not None:
        ai_manager.plan.return_value = plan_result
    registry.register("ai_manager", ai_manager)

    return registry


class TestEvolutionAI:
    """Unit tests for the EvolutionAI service wrapper."""

    def test_plan_uses_ask_routed_with_text_generation(self):
        registry = _make_registry()
        evo = EvolutionAI(registry)

        result = evo.plan("improve the project")

        router = registry.get("ai_router")
        router.ask_routed.assert_called_once()
        call_kwargs = router.ask_routed.call_args[1]
        caps = call_kwargs.get("required_capabilities")
        assert caps is not None
        assert ProviderCapability.TEXT_GENERATION in caps
        assert router.ask_routed.call_args[0][0] == "improve the project"

    def test_generate_uses_ask_routed_with_text_generation(self):
        registry = _make_registry()
        evo = EvolutionAI(registry)

        result = evo.generate("write some code")

        router = registry.get("ai_router")
        router.ask_routed.assert_called_once()
        call_kwargs = router.ask_routed.call_args[1]
        caps = call_kwargs.get("required_capabilities")
        assert caps is not None
        assert ProviderCapability.TEXT_GENERATION in caps
        assert router.ask_routed.call_args[0][0] == "write some code"

    def test_autofix_uses_ask_routed_with_text_generation(self):
        registry = _make_registry()
        evo = EvolutionAI(registry)

        result = evo.autofix("fix this bug")

        router = registry.get("ai_router")
        router.ask_routed.assert_called_once()
        call_kwargs = router.ask_routed.call_args[1]
        caps = call_kwargs.get("required_capabilities")
        assert caps is not None
        assert ProviderCapability.TEXT_GENERATION in caps
        assert router.ask_routed.call_args[0][0] == "fix this bug"

    def test_plan_returns_ai_response(self):
        expected = _make_ai_response("plan text")
        registry = _make_registry(ai_response=expected)
        evo = EvolutionAI(registry)

        result = evo.plan("objective")

        assert str(result) == "plan text"
        assert result.provider == "test"

    def test_generate_returns_ai_response(self):
        expected = _make_ai_response("generated code", provider="mock")
        registry = _make_registry(ai_response=expected)
        evo = EvolutionAI(registry)

        result = evo.generate("prompt")

        assert str(result) == "generated code"
        assert result.provider == "mock"

    def test_autofix_returns_ai_response(self):
        expected = _make_ai_response("fixed code", latency_ms=42.0)
        registry = _make_registry(ai_response=expected)
        evo = EvolutionAI(registry)

        result = evo.autofix("fix")

        assert str(result) == "fixed code"
        assert result.latency_ms == 42.0

    def test_plan_preserves_metadata(self):
        meta = {"routing_strategy": "preferred", "fallback_history": []}
        expected = _make_ai_response("plan with meta", metadata=meta)
        registry = _make_registry(ai_response=expected)
        evo = EvolutionAI(registry)

        result = evo.plan("objective")

        assert result.metadata.get("routing_strategy") == "preferred"


class TestEvolutionAIIntegration:
    """Tests that planner/generator/autofix use EvolutionAI (not direct AIManager)."""

    def test_planner_uses_evolution_ai(self, monkeypatch, tmp_path):
        ai_response = _make_ai_response("## Plan\n1. Do thing")
        registry = _make_registry(ai_response=ai_response)

        prompt_file = Path(tmp_path / "data" / "ai_prompt.txt")
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text("improve the project", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        from app.evolution.planner import EvolutionPlanner

        planner = EvolutionPlanner(registry)
        result = planner.create_plan()

        router = registry.get("ai_router")
        router.ask_routed.assert_called_once()
        caps = router.ask_routed.call_args[1]["required_capabilities"]
        assert ProviderCapability.TEXT_GENERATION in caps

        plan_file = Path("data/improvement_plan.md")
        assert plan_file.read_text(encoding="utf-8") == "## Plan\n1. Do thing"
        assert "## Plan" in result

    def test_planner_writes_plan_file(self, monkeypatch, tmp_path):
        ai_response = _make_ai_response("numbered plan")
        registry = _make_registry(ai_response=ai_response)

        prompt_file = Path(tmp_path / "data" / "ai_prompt.txt")
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text("plan it", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        from app.evolution.planner import EvolutionPlanner

        planner = EvolutionPlanner(registry)
        result = planner.create_plan()

        plan_file = Path("data/improvement_plan.md")
        assert plan_file.exists()
        assert plan_file.read_text(encoding="utf-8") == "numbered plan"

    def test_generator_uses_evolution_ai(self, monkeypatch, tmp_path):
        ai_response = _make_ai_response("def foo(): pass")
        registry = _make_registry(ai_response=ai_response)

        monkeypatch.chdir(tmp_path)

        source_file = tmp_path / "app" / "skills" / "loader.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("pass", encoding="utf-8")

        tree_file = tmp_path / "data" / "project_tree.txt"
        tree_file.parent.mkdir(parents=True, exist_ok=True)
        tree_file.write_text("app/skills/loader.py", encoding="utf-8")

        from app.evolution.context_builder import ContextBuilder
        orig_build = ContextBuilder.build
        ContextBuilder.build = MagicMock(return_value=tree_file)

        try:
            from app.evolution.generator import CodeGenerator

            generator = CodeGenerator(registry)
            output = generator.generate_task(
                "add function", str(source_file),
                output=str(tmp_path / "generated_patch.py"),
            )

            router = registry.get("ai_router")
            router.ask_routed.assert_called_once()
            caps = router.ask_routed.call_args[1]["required_capabilities"]
            assert ProviderCapability.TEXT_GENERATION in caps

            patch = Path(output)
            assert patch.read_text(encoding="utf-8") == "def foo(): pass"
        finally:
            ContextBuilder.build = orig_build

    def test_autofixer_uses_evolution_ai(self, monkeypatch, tmp_path):
        ai_response = _make_ai_response("def fixed(): pass")
        registry = _make_registry(ai_response=ai_response)

        monkeypatch.chdir(tmp_path)

        review_file = tmp_path / "data" / "review_report.txt"
        review_file.parent.mkdir(parents=True, exist_ok=True)
        review_file.write_text("WARNING: unused import", encoding="utf-8")

        patch_file = tmp_path / "data" / "generated_patch.py"
        patch_file.write_text("def broken(): pass", encoding="utf-8")

        from app.evolution.autofix import AutoFixer

        fixer = AutoFixer(registry)
        result = fixer.fix(
            review_file=str(review_file),
            patch_file=str(patch_file),
        )

        router = registry.get("ai_router")
        router.ask_routed.assert_called_once()
        caps = router.ask_routed.call_args[1]["required_capabilities"]
        assert ProviderCapability.TEXT_GENERATION in caps

        assert patch_file.read_text(encoding="utf-8") == "def fixed(): pass"
        assert result == str(patch_file)

    def test_autofixer_skips_ai_when_no_issues(self, monkeypatch, tmp_path):
        registry = _make_registry()
        monkeypatch.chdir(tmp_path)

        review_file = tmp_path / "data" / "review_report.txt"
        review_file.parent.mkdir(parents=True, exist_ok=True)
        review_file.write_text("Syntax OK: True", encoding="utf-8")

        patch_file = tmp_path / "data" / "generated_patch.py"
        patch_file.write_text("def ok(): pass", encoding="utf-8")

        from app.evolution.autofix import AutoFixer

        fixer = AutoFixer(registry)
        result = fixer.fix(
            review_file=str(review_file),
            patch_file=str(patch_file),
        )

        router = registry.get("ai_router")
        router.ask_routed.assert_not_called()
        assert result == str(patch_file)
        assert patch_file.read_text(encoding="utf-8") == "def ok(): pass"


class TestEvolutionAIRegistration:
    """Tests that EvolutionAI is registered in the kernel via registry."""

    def test_can_construct_from_registry(self):
        registry = _make_registry()
        evo = EvolutionAI(registry)
        assert evo._ai is not None
        assert evo._router is not None

    def test_registry_round_trip(self):
        registry = _make_registry()
        registry.register("evolution_ai", EvolutionAI(registry))
        retrieved = registry.get("evolution_ai")
        assert isinstance(retrieved, EvolutionAI)


class TestEvolutionBrainCreatesComponentsWithRegistry:
    """Integration-lite: verify brain passes registry to AI components."""

    def test_evolution_brain_accepts_registry(self):
        from app.evolution.brain import EvolutionBrain
        brain = EvolutionBrain(registry=MagicMock())
        assert brain._registry is not None

    def test_evolution_brain_defaults_to_none(self):
        from app.evolution.brain import EvolutionBrain
        brain = EvolutionBrain()
        assert brain._registry is None
