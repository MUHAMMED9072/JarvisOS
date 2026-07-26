from __future__ import annotations

import json

import pytest

from app.ai.manager import AIManager, _try_parse_json
from app.ai.planning import (
    DEFAULT_PLAN_PROMPT,
    PLAN_SCHEMA,
    Plan,
    PlanAction,
    PlanError,
    PlanParseError,
    PlanResult,
    PlanStep,
    PlanValidationError,
    PlanValidationResult,
    _find_circular_dependencies,
    parse_plan,
    validate_plan,
)
from app.ai.providers.base import AIProvider, AIResponse, ProviderCapability
from app.ai.structured import StructuredSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step(
    step_id: str = "step_1",
    title: str = "Step 1",
    action_type: PlanAction = PlanAction.TASK,
    depends_on: list[str] | None = None,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        title=title,
        action_type=action_type,
        description=f"Description for {step_id}",
        depends_on=tuple(depends_on or []),
    )


def _make_plan(
    steps: tuple[PlanStep, ...] = (),
    title: str = "Test Plan",
    objective: str = "Test objective",
) -> Plan:
    if not steps:
        steps = (_make_step(),)
    return Plan(
        title=title,
        objective=objective,
        steps=steps,
    )


def _make_plan_data(
    steps: list[dict] | None = None,
    title: str = "Test Plan",
    objective: str = "Test objective",
) -> dict:
    if steps is None:
        steps = [{
            "id": "step_1",
            "title": "Step 1",
            "action_type": "task",
            "description": "Do something",
            "depends_on": [],
        }]
    return {
        "title": title,
        "objective": objective,
        "steps": steps,
    }


class _PlanningMockProvider(AIProvider):
    def __init__(
        self,
        provider_name: str = "planner",
        capabilities: frozenset | None = None,
        plan_data: dict | None = None,
    ):
        self.provider_name = provider_name
        self.capabilities = capabilities or frozenset({
            ProviderCapability.TEXT_GENERATION,
            ProviderCapability.REASONING,
            ProviderCapability.JSON_OUTPUT,
            ProviderCapability.STREAMING,
        })
        self._plan_data = plan_data or _make_plan_data()
        self._called_with_schema = None

    def generate(self, prompt: str, **kwargs) -> AIResponse:
        schema = kwargs.get("schema")
        structured_meta = {}
        if schema is not None:
            self._called_with_schema = schema
            structured_meta["structured"] = {"data": self._plan_data}
        return AIResponse(
            json.dumps(self._plan_data),
            provider=self.provider_name,
            model="test-model",
            latency_ms=1.0,
            metadata=structured_meta,
        )

    def check_availability(self) -> bool:
        return True


class _NoReasoningMockProvider(AIProvider):
    def __init__(self, provider_name: str = "noreason"):
        self.provider_name = provider_name
        self.capabilities = frozenset({
            ProviderCapability.TEXT_GENERATION,
            ProviderCapability.STREAMING,
        })

    def generate(self, prompt: str, **kwargs) -> AIResponse:
        return AIResponse(
            f"{self.provider_name}: {prompt}",
            provider=self.provider_name,
            model="test",
            latency_ms=0.0,
            metadata={},
        )

    def check_availability(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# PlanAction
# ---------------------------------------------------------------------------


class TestPlanAction:
    def test_action_values(self) -> None:
        assert PlanAction.TASK.value == "task"
        assert PlanAction.QUERY.value == "query"
        assert PlanAction.DECISION.value == "decision"
        assert PlanAction.PARALLEL.value == "parallel"
        assert PlanAction.CONDITIONAL.value == "conditional"
        assert PlanAction.INPUT.value == "input"
        assert PlanAction.OUTPUT.value == "output"

    def test_all_members_accessible(self) -> None:
        actions = set(PlanAction)
        assert len(actions) == 7


# ---------------------------------------------------------------------------
# PlanStep
# ---------------------------------------------------------------------------


class TestPlanStep:
    def test_create_minimal(self) -> None:
        step = PlanStep(id="s1", title="Step 1")
        assert step.id == "s1"
        assert step.action_type == PlanAction.TASK
        assert step.depends_on == ()

    def test_create_with_dependencies(self) -> None:
        step = PlanStep(
            id="s3",
            title="Step 3",
            action_type=PlanAction.QUERY,
            depends_on=("s1", "s2"),
            conditions="if ready",
        )
        assert step.depends_on == ("s1", "s2")
        assert step.conditions == "if ready"

    def test_create_with_metadata(self) -> None:
        step = PlanStep(id="s1", title="S1", metadata={"key": "val"})
        assert step.metadata == {"key": "val"}

    def test_frozen(self) -> None:
        step = PlanStep(id="s1", title="S1")
        with pytest.raises(AttributeError):
            step.id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_create_minimal(self) -> None:
        plan = Plan()
        assert plan.steps == ()
        assert plan.id is not None

    def test_create_with_steps(self) -> None:
        s = _make_step()
        plan = Plan(title="P", objective="O", steps=(s,))
        assert len(plan.steps) == 1
        assert plan.steps[0] == s

    def test_id_uniqueness(self) -> None:
        plan1 = Plan()
        plan2 = Plan()
        assert plan1.id != plan2.id

    def test_created_at_set(self) -> None:
        plan = Plan()
        assert plan.created_at > 0

    def test_metadata(self) -> None:
        plan = Plan(title="P", objective="O", steps=(_make_step(),), metadata={"v": "1"})
        assert plan.metadata == {"v": "1"}

    def test_frozen(self) -> None:
        plan = Plan()
        with pytest.raises(AttributeError):
            plan.title = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PlanResult
# ---------------------------------------------------------------------------


class TestPlanResult:
    def test_create(self) -> None:
        plan = _make_plan()
        result = PlanResult(
            plan=plan, provider="test", model="m",
            duration_ms=1.0, valid=True,
        )
        assert result.plan == plan
        assert result.valid is True

    def test_metadata(self) -> None:
        result = PlanResult(
            plan=_make_plan(), provider="t", model="m",
            duration_ms=1.0, valid=True,
            metadata={"key": "val"},
        )
        assert result.metadata["key"] == "val"

    def test_validation_errors(self) -> None:
        result = PlanResult(
            plan=_make_plan(), provider="t", model="m",
            duration_ms=1.0, valid=False,
            validation_errors=["error"],
        )
        assert result.validation_errors == ["error"]


# ---------------------------------------------------------------------------
# PlanValidationResult
# ---------------------------------------------------------------------------


class TestPlanValidationResult:
    def test_valid_default(self) -> None:
        r = PlanValidationResult(valid=True)
        assert r.errors == []
        assert r.warnings == []

    def test_with_errors(self) -> None:
        r = PlanValidationResult(valid=False, errors=["e1"])
        assert r.errors == ["e1"]


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------


class TestCircularDependencyDetection:
    def test_no_cycles(self) -> None:
        steps = (
            _make_step("s1", depends_on=[]),
            _make_step("s2", depends_on=["s1"]),
            _make_step("s3", depends_on=["s2"]),
        )
        assert _find_circular_dependencies(steps) == []

    def test_direct_cycle(self) -> None:
        steps = (
            _make_step("s1", depends_on=["s1"]),
        )
        cycles = _find_circular_dependencies(steps)
        assert len(cycles) == 1
        assert "s1" in cycles[0]

    def test_indirect_cycle(self) -> None:
        steps = (
            _make_step("s1", depends_on=["s2"]),
            _make_step("s2", depends_on=["s3"]),
            _make_step("s3", depends_on=["s1"]),
        )
        cycles = _find_circular_dependencies(steps)
        assert len(cycles) >= 1

    def test_no_dependencies(self) -> None:
        steps = (
            _make_step("s1", depends_on=[]),
            _make_step("s2", depends_on=[]),
        )
        assert _find_circular_dependencies(steps) == []

    def test_self_reference_cycle(self) -> None:
        steps = (_make_step("s1", depends_on=["s1"]),)
        cycles = _find_circular_dependencies(steps)
        assert len(cycles) == 1
        assert "s1" in cycles[0]


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------


class TestPlanValidation:
    def test_valid_plan(self) -> None:
        plan = _make_plan()
        result = validate_plan(plan)
        assert result.valid is True

    def test_empty_steps(self) -> None:
        plan = Plan(title="P", objective="O")
        result = validate_plan(plan)
        assert result.valid is False
        assert any("no steps" in e for e in result.errors)

    def test_no_objective(self) -> None:
        plan = Plan(title="P", steps=(_make_step(),))
        result = validate_plan(plan)
        assert result.valid is False
        assert any("objective" in e for e in result.errors)

    def test_no_title(self) -> None:
        plan = Plan(objective="O", steps=(_make_step(),))
        result = validate_plan(plan)
        assert result.valid is False
        assert any("title" in e for e in result.errors)

    def test_duplicate_step_id(self) -> None:
        steps = (_make_step("s1"), _make_step("s1"))
        plan = _make_plan(steps)
        result = validate_plan(plan)
        assert result.valid is False
        assert any("Duplicate" in e for e in result.errors)

    def test_empty_step_id(self) -> None:
        step = PlanStep(id="", title="No ID")
        plan = Plan(title="P", objective="O", steps=(step,))
        result = validate_plan(plan)
        assert result.valid is False

    def test_step_no_title(self) -> None:
        step = PlanStep(id="s1", title="")
        plan = Plan(title="P", objective="O", steps=(step,))
        result = validate_plan(plan)
        assert result.valid is False

    def test_invalid_dependency_reference(self) -> None:
        steps = (
            _make_step("s1", depends_on=["nonexistent"]),
        )
        plan = _make_plan(steps)
        result = validate_plan(plan)
        assert result.valid is False
        assert any("nonexistent" in e for e in result.errors)

    def test_circular_dependency(self) -> None:
        steps = (
            _make_step("s1", depends_on=["s2"]),
            _make_step("s2", depends_on=["s1"]),
        )
        plan = _make_plan(steps)
        result = validate_plan(plan)
        assert result.valid is False
        assert any("Circular" in e for e in result.errors)

    def test_invalid_plan_metadata(self) -> None:
        plan = Plan(title="P", objective="O", steps=(_make_step(),), metadata="str")  # type: ignore[arg-type]
        result = validate_plan(plan)
        assert result.valid is False

    def test_invalid_step_metadata(self) -> None:
        step = PlanStep(id="s1", title="S1", metadata="str")  # type: ignore[arg-type]
        plan = Plan(title="P", objective="O", steps=(step,))
        result = validate_plan(plan)
        assert result.valid is False

    def test_validate_multiple_errors(self) -> None:
        plan = Plan(title="", objective="")
        result = validate_plan(plan)
        assert result.valid is False
        assert len(result.errors) >= 2


# ---------------------------------------------------------------------------
# Plan parsing
# ---------------------------------------------------------------------------


class TestPlanParsing:
    def test_parse_valid_data(self) -> None:
        data = _make_plan_data()
        plan = parse_plan(data)
        assert plan.title == "Test Plan"
        assert plan.objective == "Test objective"
        assert len(plan.steps) == 1
        assert plan.steps[0].id == "step_1"
        assert plan.steps[0].action_type == PlanAction.TASK

    def test_parse_multiple_steps(self) -> None:
        data = _make_plan_data(steps=[
            {"id": "s1", "title": "First", "action_type": "query",
             "description": "Query data", "depends_on": []},
            {"id": "s2", "title": "Second", "action_type": "task",
             "description": "Process", "depends_on": ["s1"]},
        ])
        plan = parse_plan(data)
        assert len(plan.steps) == 2
        assert plan.steps[0].action_type == PlanAction.QUERY
        assert plan.steps[1].depends_on == ("s1",)

    def test_parse_with_unknown_action_type(self) -> None:
        data = _make_plan_data(steps=[{
            "id": "s1", "title": "S1", "action_type": "unknown_type",
        }])
        plan = parse_plan(data)
        assert plan.steps[0].action_type == PlanAction.TASK

    def test_parse_missing_steps_defaults_empty(self) -> None:
        data = {"title": "T", "objective": "O"}
        plan = parse_plan(data)
        assert plan.steps == ()

    def test_parse_with_conditions(self) -> None:
        data = _make_plan_data(steps=[{
            "id": "s1", "title": "S1", "action_type": "conditional",
            "conditions": "if x > 5", "depends_on": [],
        }])
        plan = parse_plan(data)
        assert plan.steps[0].conditions == "if x > 5"
        assert plan.steps[0].action_type == PlanAction.CONDITIONAL

    def test_parse_with_metadata(self) -> None:
        data = _make_plan_data(steps=[{
            "id": "s1", "title": "S1", "action_type": "task",
            "metadata": {"key": "val"},
        }])
        plan = parse_plan(data)
        assert plan.steps[0].metadata == {"key": "val"}

    def test_parse_invalid_data_raises(self) -> None:
        with pytest.raises(PlanParseError):
            parse_plan({"steps": [None]})  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# PLAN_SCHEMA
# ---------------------------------------------------------------------------


class TestPlanSchema:
    def test_schema_is_structured_schema(self) -> None:
        assert isinstance(PLAN_SCHEMA, StructuredSchema)

    def test_schema_name(self) -> None:
        assert PLAN_SCHEMA.name == "plan"

    def test_schema_has_required_fields(self) -> None:
        required = PLAN_SCHEMA.schema.get("required", [])
        assert "title" in required
        assert "objective" in required
        assert "steps" in required

    def test_schema_has_steps_items(self) -> None:
        steps = PLAN_SCHEMA.schema["properties"]["steps"]
        assert steps["type"] == "array"
        items = steps["items"]
        assert "id" in items["required"]
        assert "title" in items["required"]
        assert "action_type" in items["required"]


# ---------------------------------------------------------------------------
# DEFAULT_PLAN_PROMPT
# ---------------------------------------------------------------------------


class TestDefaultPlanPrompt:
    def test_prompt_contains_objective(self) -> None:
        prompt = DEFAULT_PLAN_PROMPT.format(objective="Build X")
        assert "Build X" in prompt

    def test_prompt_formats_correctly(self) -> None:
        prompt = DEFAULT_PLAN_PROMPT.format(objective="Test")
        assert "{objective}" not in prompt


# ---------------------------------------------------------------------------
# _try_parse_json
# ---------------------------------------------------------------------------


class TestTryParseJson:
    def test_parse_valid_json(self) -> None:
        result = _try_parse_json('{"key": "val"}')
        assert result == {"key": "val"}

    def test_parse_json_from_code_fence(self) -> None:
        result = _try_parse_json("```json\n{\"key\": \"val\"}\n```")
        assert result == {"key": "val"}

    def test_parse_json_from_markdown(self) -> None:
        result = _try_parse_json('Some text\n```\n{"key": "val"}\n```\nmore')
        assert result == {"key": "val"}

    def test_parse_extract_brace_block(self) -> None:
        result = _try_parse_json('text {"key": "val"} text')
        assert result == {"key": "val"}

    def test_parse_invalid_returns_empty(self) -> None:
        result = _try_parse_json("not json")
        assert result == {}


# ---------------------------------------------------------------------------
# AIManager plan() integration
# ---------------------------------------------------------------------------


class TestAIManagerPlanning:
    def test_plan_with_default_prompt(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        result = manager.plan("Test objective", provider="planner")
        assert isinstance(result, PlanResult)
        assert result.plan.objective == "Test objective"
        assert result.valid is True

    def test_plan_with_routed_provider(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        from app.ai.routing import RoutingConfig
        manager.router.routing_config = RoutingConfig(providers=("planner",))
        result = manager.plan("Routed plan")
        assert isinstance(result, PlanResult)
        assert result.plan is not None

    def test_plan_rejects_provider_without_reasoning(self) -> None:
        manager = AIManager()
        manager.router.providers["noreason"] = _NoReasoningMockProvider("noreason")
        from app.ai.providers.base import AIProviderError
        with pytest.raises(AIProviderError, match="REASONING"):
            manager.plan("Objective", provider="noreason")

    def test_plan_skips_provider_without_reasoning_on_routed(self) -> None:
        manager = AIManager()
        manager.router.providers["bad"] = _NoReasoningMockProvider("bad")
        manager.router.providers["good"] = _PlanningMockProvider("good")
        from app.ai.routing import RoutingConfig
        manager.router.routing_config = RoutingConfig(providers=("bad", "good"))
        result = manager.plan("Routed")
        assert result.provider == "good"
        assert result.valid is True

    def test_plan_all_fail_without_reasoning_raises(self) -> None:
        manager = AIManager()
        manager.router.providers["bad1"] = _NoReasoningMockProvider("bad1")
        manager.router.providers["bad2"] = _NoReasoningMockProvider("bad2")
        from app.ai.routing import RoutingConfig
        from app.ai.providers.base import AllProvidersFailedError
        manager.router.routing_config = RoutingConfig(providers=("bad1", "bad2"))
        with pytest.raises(AllProvidersFailedError):
            manager.plan("Will fail")

    def test_plan_metadata_contains_provider_and_model(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        result = manager.plan("Test", provider="planner")
        assert result.metadata["provider"] == "planner"
        assert result.metadata["model"] == "test-model"

    def test_plan_metadata_contains_validation_status(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        result = manager.plan("Test", provider="planner")
        assert result.metadata["validation_status"] == "valid"

    def test_plan_metadata_contains_planning_duration(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        result = manager.plan("Test", provider="planner")
        assert result.metadata["planning_duration_ms"] >= 0

    def test_plan_metadata_contains_template_info_when_used(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        from app.ai.templates import PromptTemplate, PromptVariable
        t = PromptTemplate(
            name="plan_prompt",
            description="",
            template="Plan: {{objective}}",
            variables=[PromptVariable(name="objective")],
        )
        manager.template_registry.register(t)
        result = manager.plan(
            "Custom template", provider="planner",
            prompt_template="plan_prompt",
            template_variables={"objective": "Custom template"},
        )
        assert result.metadata.get("template_name") == "plan_prompt"

    def test_plan_with_custom_planning_prompt(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        result = manager.plan(
            "Custom", provider="planner",
            planning_prompt="Custom: {objective}",
        )
        assert result.plan is not None

    def test_plan_invalid_plan_data_sets_valid_false(self) -> None:
        manager = AIManager()
        bad_data = _make_plan_data(steps=[])
        provider = _PlanningMockProvider("planner", plan_data=bad_data)
        manager.router.providers["planner"] = provider
        result = manager.plan("Test", provider="planner")
        assert result.valid is False
        assert len(result.validation_errors) > 0

    def test_plan_validation_errors_in_result(self) -> None:
        manager = AIManager()
        bad_data = {"title": "", "objective": "", "steps": []}
        provider = _PlanningMockProvider("planner", plan_data=bad_data)
        manager.router.providers["planner"] = provider
        result = manager.plan("Test", provider="planner")
        assert result.valid is False
        assert len(result.validation_errors) >= 1

    def test_plan_passes_schema_to_provider(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        manager.plan("Test", provider="planner")
        assert provider._called_with_schema is not None
        assert provider._called_with_schema.name == "plan"

    def test_plan_with_conversation(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        conv = manager.create_conversation()
        result = manager.plan(
            "Test", provider="planner", conversation_id=conv.conversation_id,
        )
        assert result.metadata.get("conversation_id") == conv.conversation_id

    def test_plan_with_nonexistent_conversation_raises(self) -> None:
        manager = AIManager()
        with pytest.raises(ValueError, match="not found"):
            manager.plan("Test", provider="planner", conversation_id="nonexistent")

    def test_plan_preserves_routing_strategy_metadata(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        from app.ai.routing import RoutingConfig, RoutingStrategy
        manager.router.routing_config = RoutingConfig(
            providers=("planner",),
            strategy=RoutingStrategy.PREFERRED,
        )
        result = manager.plan("Test")
        assert result.metadata.get("routing_strategy") == "PREFERRED"

    def test_plan_with_default_and_routed_equivalent(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        from app.ai.routing import RoutingConfig
        manager.router.routing_config = RoutingConfig(providers=("planner",))
        result_provider = manager.plan("Test", provider="planner")
        result_routed = manager.plan("Test")
        assert result_provider.plan.objective == result_routed.plan.objective

    def test_plan_duration_ms_from_provider(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("planner")
        manager.router.providers["planner"] = provider
        result = manager.plan("Test", provider="planner")
        assert result.duration_ms > 0


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestPlanErrorHierarchy:
    def test_base_error(self) -> None:
        assert issubclass(PlanError, Exception)

    def test_parse_error_subclass(self) -> None:
        assert issubclass(PlanParseError, PlanError)

    def test_validation_error_subclass(self) -> None:
        assert issubclass(PlanValidationError, PlanError)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_existing_ask_unchanged(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("mock")
        manager.router.providers["mock"] = provider
        result = manager.ask("mock", "hello")
        assert isinstance(result, str) and len(result) > 0

    def test_existing_ask_stream_unchanged(self) -> None:
        manager = AIManager()
        provider = _PlanningMockProvider("mock")
        manager.router.providers["mock"] = provider
        stream = manager.ask_stream("mock", "hello")
        chunks = list(stream)
        assert len(chunks) >= 1
