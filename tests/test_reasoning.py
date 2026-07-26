from __future__ import annotations

import pytest

from app.ai.manager import AIManager
from app.ai.providers.base import AIProvider, AIResponse, ProviderCapability
from app.ai.reasoning import (
    DEFAULT_REASONING_PROMPT,
    REASONING_SCHEMA,
    ReasoningChain,
    ReasoningError,
    ReasoningParseError,
    ReasoningResult,
    ReasoningStep,
    ReasoningStepType,
    ReasoningValidationError,
    ReasoningValidationResult,
    _find_circular_dependencies,
    parse_reasoning,
    validate_reasoning,
)
from app.ai.structured import StructuredSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step(
    step_id: str = "step_1",
    title: str = "Step 1",
    step_type: ReasoningStepType = ReasoningStepType.ANALYSIS,
    depends_on: list[str] | None = None,
    confidence: float = 1.0,
) -> ReasoningStep:
    return ReasoningStep(
        id=step_id,
        title=title,
        step_type=step_type,
        description=f"Description for {step_id}",
        depends_on=tuple(depends_on or []),
        confidence=confidence,
    )


def _make_chain(
    steps: tuple[ReasoningStep, ...] = (),
    objective: str = "Test objective",
    conclusion: str = "Test conclusion",
    confidence: float = 1.0,
) -> ReasoningChain:
    if not steps:
        steps = (_make_step(),)
    return ReasoningChain(
        objective=objective,
        steps=steps,
        conclusion=conclusion,
        confidence=confidence,
    )


def _make_chain_data(
    steps: list[dict] | None = None,
    objective: str = "Test objective",
    conclusion: str = "Test conclusion",
    confidence: float = 1.0,
) -> dict:
    if steps is None:
        steps = [{
            "id": "step_1",
            "title": "Step 1",
            "step_type": "analysis",
            "description": "Analyze the problem",
            "depends_on": [],
            "confidence": 1.0,
        }]
    return {
        "objective": objective,
        "conclusion": conclusion,
        "confidence": confidence,
        "steps": steps,
    }


class _ReasoningMockProvider(AIProvider):
    def __init__(
        self,
        provider_name: str = "reasoner",
        capabilities: frozenset | None = None,
        chain_data: dict | None = None,
    ):
        self.provider_name = provider_name
        self.capabilities = capabilities or frozenset({
            ProviderCapability.TEXT_GENERATION,
            ProviderCapability.REASONING,
            ProviderCapability.JSON_OUTPUT,
            ProviderCapability.STREAMING,
        })
        self._chain_data = chain_data or _make_chain_data()
        self._called_with_schema = None

    def generate(self, prompt: str, **kwargs) -> AIResponse:
        schema = kwargs.get("schema")
        structured_meta = {}
        if schema is not None:
            self._called_with_schema = schema
            structured_meta["structured"] = {"data": self._chain_data}
        import json
        return AIResponse(
            json.dumps(self._chain_data),
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
# ReasoningStepType
# ---------------------------------------------------------------------------


class TestReasoningStepType:
    def test_values(self) -> None:
        assert ReasoningStepType.DEDUCTION.value == "deduction"
        assert ReasoningStepType.INDUCTION.value == "induction"
        assert ReasoningStepType.ABDUCTION.value == "abduction"
        assert ReasoningStepType.ANALOGY.value == "analogy"
        assert ReasoningStepType.ANALYSIS.value == "analysis"
        assert ReasoningStepType.EVALUATION.value == "evaluation"
        assert ReasoningStepType.COMPARISON.value == "comparison"

    def test_all_members(self) -> None:
        assert len(set(ReasoningStepType)) == 7


# ---------------------------------------------------------------------------
# ReasoningStep
# ---------------------------------------------------------------------------


class TestReasoningStep:
    def test_create_minimal(self) -> None:
        step = ReasoningStep(id="s1", title="Step 1")
        assert step.step_type == ReasoningStepType.ANALYSIS
        assert step.confidence == 1.0
        assert step.depends_on == ()

    def test_create_full(self) -> None:
        step = ReasoningStep(
            id="s1",
            title="Deduce",
            step_type=ReasoningStepType.DEDUCTION,
            evidence="All men are mortal",
            depends_on=("s0",),
            confidence=0.95,
            metadata={"source": "logic"},
        )
        assert step.evidence == "All men are mortal"
        assert step.confidence == 0.95
        assert step.metadata == {"source": "logic"}

    def test_frozen(self) -> None:
        step = ReasoningStep(id="s1", title="S1")
        with pytest.raises(AttributeError):
            step.id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ReasoningChain
# ---------------------------------------------------------------------------


class TestReasoningChain:
    def test_create_minimal(self) -> None:
        chain = ReasoningChain()
        assert chain.steps == ()
        assert chain.conclusion == ""

    def test_create_with_steps(self) -> None:
        s = _make_step()
        chain = ReasoningChain(objective="O", steps=(s,), conclusion="C", confidence=0.9)
        assert len(chain.steps) == 1
        assert chain.conclusion == "C"
        assert chain.confidence == 0.9

    def test_id_uniqueness(self) -> None:
        c1 = ReasoningChain()
        c2 = ReasoningChain()
        assert c1.id != c2.id

    def test_assumptions(self) -> None:
        chain = ReasoningChain(
            objective="O", steps=(_make_step(),), conclusion="C",
            assumptions=("A1", "A2"),
        )
        assert chain.assumptions == ("A1", "A2")

    def test_created_at_set(self) -> None:
        chain = ReasoningChain(
            objective="O", steps=(_make_step(),), conclusion="C",
        )
        assert chain.created_at > 0

    def test_frozen(self) -> None:
        chain = ReasoningChain()
        with pytest.raises(AttributeError):
            chain.objective = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ReasoningResult
# ---------------------------------------------------------------------------


class TestReasoningResult:
    def test_create(self) -> None:
        chain = _make_chain()
        result = ReasoningResult(
            chain=chain, provider="test", model="m",
            duration_ms=1.0, valid=True,
        )
        assert result.chain == chain
        assert result.valid is True

    def test_metadata(self) -> None:
        result = ReasoningResult(
            chain=_make_chain(), provider="t", model="m",
            duration_ms=1.0, valid=True,
            metadata={"key": "val"},
        )
        assert result.metadata["key"] == "val"

    def test_validation_errors(self) -> None:
        result = ReasoningResult(
            chain=_make_chain(), provider="t", model="m",
            duration_ms=1.0, valid=False,
            validation_errors=["error"],
        )
        assert result.validation_errors == ["error"]


# ---------------------------------------------------------------------------
# ReasoningValidationResult
# ---------------------------------------------------------------------------


class TestReasoningValidationResult:
    def test_valid_default(self) -> None:
        r = ReasoningValidationResult(valid=True)
        assert r.errors == []
        assert r.warnings == []

    def test_with_errors(self) -> None:
        r = ReasoningValidationResult(valid=False, errors=["e1"])
        assert r.errors == ["e1"]


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------


class TestCircularDependencyDetection:
    def test_no_cycles(self) -> None:
        steps = (
            _make_step("s1", depends_on=[]),
            _make_step("s2", depends_on=["s1"]),
        )
        assert _find_circular_dependencies(steps) == []

    def test_direct_cycle(self) -> None:
        steps = (_make_step("s1", depends_on=["s1"]),)
        cycles = _find_circular_dependencies(steps)
        assert len(cycles) == 1

    def test_indirect_cycle(self) -> None:
        steps = (
            _make_step("s1", depends_on=["s2"]),
            _make_step("s2", depends_on=["s3"]),
            _make_step("s3", depends_on=["s1"]),
        )
        cycles = _find_circular_dependencies(steps)
        assert len(cycles) >= 1

    def test_no_deps(self) -> None:
        steps = (_make_step("s1"), _make_step("s2"))
        assert _find_circular_dependencies(steps) == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestReasoningValidation:
    def test_valid_chain(self) -> None:
        chain = _make_chain()
        result = validate_reasoning(chain)
        assert result.valid is True

    def test_no_objective(self) -> None:
        chain = ReasoningChain(steps=(_make_step(),), conclusion="C")
        result = validate_reasoning(chain)
        assert result.valid is False
        assert any("objective" in e for e in result.errors)

    def test_no_steps(self) -> None:
        chain = ReasoningChain(objective="O", conclusion="C")
        result = validate_reasoning(chain)
        assert result.valid is False
        assert any("no steps" in e for e in result.errors)

    def test_duplicate_step_id(self) -> None:
        steps = (_make_step("s1"), _make_step("s1"))
        chain = _make_chain(steps)
        result = validate_reasoning(chain)
        assert result.valid is False
        assert any("Duplicate" in e for e in result.errors)

    def test_empty_step_id(self) -> None:
        step = ReasoningStep(id="", title="No ID")
        chain = ReasoningChain(objective="O", steps=(step,), conclusion="C")
        result = validate_reasoning(chain)
        assert result.valid is False

    def test_step_no_title(self) -> None:
        step = ReasoningStep(id="s1", title="")
        chain = ReasoningChain(objective="O", steps=(step,), conclusion="C")
        result = validate_reasoning(chain)
        assert result.valid is False

    def test_invalid_dependency(self) -> None:
        steps = (_make_step("s1", depends_on=["missing"]),)
        chain = _make_chain(steps)
        result = validate_reasoning(chain)
        assert result.valid is False
        assert any("missing" in e for e in result.errors)

    def test_circular_dependency(self) -> None:
        steps = (
            _make_step("s1", depends_on=["s2"]),
            _make_step("s2", depends_on=["s1"]),
        )
        chain = _make_chain(steps)
        result = validate_reasoning(chain)
        assert result.valid is False
        assert any("Circular" in e for e in result.errors)

    def test_chain_confidence_out_of_range_high(self) -> None:
        chain = ReasoningChain(
            objective="O", steps=(_make_step(),), conclusion="C",
            confidence=1.5,
        )
        result = validate_reasoning(chain)
        assert result.valid is False
        assert any("confidence" in e for e in result.errors)

    def test_chain_confidence_out_of_range_low(self) -> None:
        chain = ReasoningChain(
            objective="O", steps=(_make_step(),), conclusion="C",
            confidence=-0.1,
        )
        result = validate_reasoning(chain)
        assert result.valid is False

    def test_step_confidence_out_of_range(self) -> None:
        steps = (_make_step("s1", confidence=2.0),)
        chain = _make_chain(steps)
        result = validate_reasoning(chain)
        assert result.valid is False
        assert any("confidence" in e for e in result.errors)

    def test_step_confidence_boundary_values(self) -> None:
        steps = (_make_step("s1", confidence=0.0), _make_step("s2", confidence=1.0))
        chain = _make_chain(steps)
        result = validate_reasoning(chain)
        assert result.valid is True

    def test_invalid_chain_metadata(self) -> None:
        chain = ReasoningChain(
            objective="O", steps=(_make_step(),), conclusion="C",
            metadata="str",  # type: ignore[arg-type]
        )
        result = validate_reasoning(chain)
        assert result.valid is False

    def test_invalid_step_metadata(self) -> None:
        step = ReasoningStep(id="s1", title="S1", metadata="str")  # type: ignore[arg-type]
        chain = ReasoningChain(objective="O", steps=(step,), conclusion="C")
        result = validate_reasoning(chain)
        assert result.valid is False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestReasoningParsing:
    def test_parse_valid(self) -> None:
        data = _make_chain_data()
        chain = parse_reasoning(data)
        assert chain.objective == "Test objective"
        assert chain.conclusion == "Test conclusion"
        assert len(chain.steps) == 1
        assert chain.steps[0].step_type == ReasoningStepType.ANALYSIS

    def test_parse_multiple_steps(self) -> None:
        data = _make_chain_data(steps=[
            {"id": "s1", "title": "Deduce", "step_type": "deduction",
             "description": "First", "depends_on": [], "confidence": 0.9},
            {"id": "s2", "title": "Conclude", "step_type": "induction",
             "description": "Second", "depends_on": ["s1"], "confidence": 0.8},
        ])
        chain = parse_reasoning(data)
        assert len(chain.steps) == 2
        assert chain.steps[0].step_type == ReasoningStepType.DEDUCTION
        assert chain.steps[1].step_type == ReasoningStepType.INDUCTION
        assert chain.steps[1].depends_on == ("s1",)

    def test_parse_unknown_type_defaults_analysis(self) -> None:
        data = _make_chain_data(steps=[{
            "id": "s1", "title": "S1", "step_type": "unknown",
        }])
        chain = parse_reasoning(data)
        assert chain.steps[0].step_type == ReasoningStepType.ANALYSIS

    def test_parse_with_assumptions(self) -> None:
        data = _make_chain_data()
        data["assumptions"] = ["A1", "A2"]
        chain = parse_reasoning(data)
        assert chain.assumptions == ("A1", "A2")

    def test_parse_with_evidence(self) -> None:
        data = _make_chain_data(steps=[{
            "id": "s1", "title": "S1", "step_type": "deduction",
            "evidence": "All men are mortal", "depends_on": [],
        }])
        chain = parse_reasoning(data)
        assert chain.steps[0].evidence == "All men are mortal"

    def test_parse_missing_steps_defaults_empty(self) -> None:
        data = {"objective": "O", "conclusion": "C"}
        chain = parse_reasoning(data)
        assert chain.steps == ()

    def test_parse_confidence_defaults(self) -> None:
        data = _make_chain_data()
        del data["confidence"]
        chain = parse_reasoning(data)
        assert chain.confidence == 1.0

    def test_parse_with_metadata(self) -> None:
        data = _make_chain_data(steps=[{
            "id": "s1", "title": "S1", "step_type": "analysis",
            "metadata": {"k": "v"},
        }])
        chain = parse_reasoning(data)
        assert chain.steps[0].metadata == {"k": "v"}

    def test_parse_invalid_data_raises(self) -> None:
        with pytest.raises(ReasoningParseError):
            parse_reasoning({"steps": [None]})  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# REASONING_SCHEMA
# ---------------------------------------------------------------------------


class TestReasoningSchema:
    def test_is_structured_schema(self) -> None:
        assert isinstance(REASONING_SCHEMA, StructuredSchema)

    def test_name(self) -> None:
        assert REASONING_SCHEMA.name == "reasoning"

    def test_required_fields(self) -> None:
        required = REASONING_SCHEMA.schema.get("required", [])
        assert "objective" in required
        assert "conclusion" in required
        assert "steps" in required

    def test_steps_items_required(self) -> None:
        items = REASONING_SCHEMA.schema["properties"]["steps"]["items"]
        assert "id" in items["required"]
        assert "title" in items["required"]
        assert "step_type" in items["required"]


# ---------------------------------------------------------------------------
# DEFAULT_REASONING_PROMPT
# ---------------------------------------------------------------------------


class TestDefaultPrompt:
    def test_contains_objective(self) -> None:
        prompt = DEFAULT_REASONING_PROMPT.format(objective="Why?")
        assert "Why?" in prompt

    def test_formatted_correctly(self) -> None:
        prompt = DEFAULT_REASONING_PROMPT.format(objective="Test")
        assert "{objective}" not in prompt


# ---------------------------------------------------------------------------
# AIManager reason() integration
# ---------------------------------------------------------------------------


class TestAIManagerReasoning:
    def test_reason_with_default_prompt(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        result = manager.reason("Why?", provider="reasoner")
        assert isinstance(result, ReasoningResult)
        assert result.chain.objective == "Test objective"
        assert result.valid is True

    def test_reason_with_routed_provider(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        from app.ai.routing import RoutingConfig
        manager.router.routing_config = RoutingConfig(providers=("reasoner",))
        result = manager.reason("Routed")
        assert isinstance(result, ReasoningResult)
        assert result.chain is not None

    def test_reason_rejects_provider_without_reasoning(self) -> None:
        manager = AIManager()
        manager.router.providers["bad"] = _NoReasoningMockProvider("bad")
        from app.ai.providers.base import AIProviderError
        with pytest.raises(AIProviderError, match="REASONING"):
            manager.reason("Why?", provider="bad")

    def test_reason_skips_provider_without_reasoning_on_routed(self) -> None:
        manager = AIManager()
        manager.router.providers["bad"] = _NoReasoningMockProvider("bad")
        manager.router.providers["good"] = _ReasoningMockProvider("good")
        from app.ai.routing import RoutingConfig
        manager.router.routing_config = RoutingConfig(providers=("bad", "good"))
        result = manager.reason("Routed")
        assert result.provider == "good"
        assert result.valid is True

    def test_reason_all_fail_raises(self) -> None:
        manager = AIManager()
        manager.router.providers["b1"] = _NoReasoningMockProvider("b1")
        manager.router.providers["b2"] = _NoReasoningMockProvider("b2")
        from app.ai.routing import RoutingConfig
        from app.ai.providers.base import AllProvidersFailedError
        manager.router.routing_config = RoutingConfig(providers=("b1", "b2"))
        with pytest.raises(AllProvidersFailedError):
            manager.reason("Will fail")

    def test_reason_metadata_contains_provider_and_model(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        result = manager.reason("Why?", provider="reasoner")
        assert result.metadata["provider"] == "reasoner"
        assert result.metadata["model"] == "test-model"

    def test_reason_metadata_validation_status(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        result = manager.reason("Why?", provider="reasoner")
        assert result.metadata["validation_status"] == "valid"

    def test_reason_metadata_duration(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        result = manager.reason("Why?", provider="reasoner")
        assert result.metadata["reasoning_duration_ms"] >= 0

    def test_reason_with_template(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        from app.ai.templates import PromptTemplate, PromptVariable
        t = PromptTemplate(
            name="reason_tmpl",
            description="",
            template="Reason: {{objective}}",
            variables=[PromptVariable(name="objective")],
        )
        manager.template_registry.register(t)
        result = manager.reason(
            "Q", provider="reasoner",
            prompt_template="reason_tmpl",
            template_variables={"objective": "Q"},
        )
        assert result.metadata.get("template_name") == "reason_tmpl"

    def test_reason_with_custom_prompt(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        result = manager.reason(
            "Why?", provider="reasoner",
            reasoning_prompt="Custom: {objective}",
        )
        assert result.chain is not None

    def test_reason_invalid_data_sets_valid_false(self) -> None:
        manager = AIManager()
        bad_data = _make_chain_data(steps=[])
        provider = _ReasoningMockProvider("reasoner", chain_data=bad_data)
        manager.router.providers["reasoner"] = provider
        result = manager.reason("Why?", provider="reasoner")
        assert result.valid is False
        assert len(result.validation_errors) > 0

    def test_reason_passes_schema_to_provider(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        manager.reason("Why?", provider="reasoner")
        assert provider._called_with_schema is not None
        assert provider._called_with_schema.name == "reasoning"

    def test_reason_with_conversation(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        conv = manager.create_conversation()
        result = manager.reason(
            "Why?", provider="reasoner",
            conversation_id=conv.conversation_id,
        )
        assert result.metadata.get("conversation_id") == conv.conversation_id

    def test_reason_with_nonexistent_conversation_raises(self) -> None:
        manager = AIManager()
        with pytest.raises(ValueError, match="not found"):
            manager.reason("Why?", provider="reasoner", conversation_id="bad")

    def test_reason_preserves_routing_strategy(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        from app.ai.routing import RoutingConfig, RoutingStrategy
        manager.router.routing_config = RoutingConfig(
            providers=("reasoner",),
            strategy=RoutingStrategy.PREFERRED,
        )
        result = manager.reason("Test")
        assert result.metadata.get("routing_strategy") == "PREFERRED"

    def test_reason_duration_ms_from_provider(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("reasoner")
        manager.router.providers["reasoner"] = provider
        result = manager.reason("Why?", provider="reasoner")
        assert result.duration_ms > 0


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestReasoningErrorHierarchy:
    def test_base(self) -> None:
        assert issubclass(ReasoningError, Exception)

    def test_parse(self) -> None:
        assert issubclass(ReasoningParseError, ReasoningError)

    def test_validation(self) -> None:
        assert issubclass(ReasoningValidationError, ReasoningError)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_existing_ask_unchanged(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("mock")
        manager.router.providers["mock"] = provider
        result = manager.ask("mock", "hello")
        assert isinstance(result, str) and len(result) > 0

    def test_existing_plan_unchanged(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("mock")
        manager.router.providers["mock"] = provider
        from app.ai.routing import RoutingConfig
        manager.router.routing_config = RoutingConfig(providers=("mock",))
        result = manager.plan("Test")
        assert result.plan is not None

    def test_both_reason_and_plan_coexist(self) -> None:
        manager = AIManager()
        provider = _ReasoningMockProvider("both")
        manager.router.providers["both"] = provider
        from app.ai.routing import RoutingConfig
        manager.router.routing_config = RoutingConfig(providers=("both",))
        r1 = manager.reason("Q", provider="both")
        r2 = manager.plan("P", provider="both")
        assert isinstance(r1, ReasoningResult)
        assert r2.plan is not None
