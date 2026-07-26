"""Tests for AI service registration, singleton behavior, and resolution."""

from __future__ import annotations

from app.ai.conversation import ConversationManager
from app.ai.manager import AIManager
from app.ai.memory_integration import MemoryAwareAI
from app.ai.planning import Plan, PlanValidationResult
from app.ai.reasoning import ReasoningChain, ReasoningValidationResult
from app.ai.router import AIRouter
from app.ai.services import (
    PlanningService,
    ReasoningService,
    StructuredService,
)
from app.ai.structured import StructuredResult, StructuredSchema
from app.ai.templates import PromptTemplateRegistry
from app.ai.tools import ToolRegistry
from app.core.registry import ServiceRegistry


# ==========================================================================
# Service registration
# ==========================================================================


class TestAIServiceRegistration:
    """AI services are registered and discoverable via the registry."""

    def test_conversation_manager_registration(self):
        reg = ServiceRegistry()
        mgr = ConversationManager()
        reg.register("conversation_manager", mgr)
        assert reg.get("conversation_manager") is mgr

    def test_template_registry_registration(self):
        reg = ServiceRegistry()
        tmpl = PromptTemplateRegistry()
        reg.register("template_registry", tmpl)
        assert reg.get("template_registry") is tmpl

    def test_tool_registry_registration(self):
        reg = ServiceRegistry()
        tools = ToolRegistry()
        reg.register("tool_registry", tools)
        assert reg.get("tool_registry") is tools

    def test_ai_router_registration(self):
        reg = ServiceRegistry()
        router = AIRouter()
        reg.register("ai_router", router)
        assert reg.get("ai_router") is router

    def test_ai_manager_registration(self):
        reg = ServiceRegistry()
        mgr = AIManager()
        reg.register("ai_manager", mgr)
        assert reg.get("ai_manager") is mgr

    def test_structured_service_registration(self):
        reg = ServiceRegistry()
        svc = StructuredService()
        reg.register("structured_service", svc)
        assert reg.get("structured_service") is svc

    def test_planning_service_registration(self):
        reg = ServiceRegistry()
        svc = PlanningService()
        reg.register("planning_service", svc)
        assert reg.get("planning_service") is svc

    def test_reasoning_service_registration(self):
        reg = ServiceRegistry()
        svc = ReasoningService()
        reg.register("reasoning_service", svc)
        assert reg.get("reasoning_service") is svc

    def test_memory_aware_ai_registration(self):
        reg = ServiceRegistry()
        ai = AIManager()
        mem_ai = MemoryAwareAI(ai)
        reg.register("memory_aware_ai", mem_ai)
        assert reg.get("memory_aware_ai") is mem_ai


# ==========================================================================
# Singleton behavior
# ==========================================================================


class TestSingletonBehavior:
    """Registered AI services behave as singletons."""

    def test_same_instance_returned(self):
        reg = ServiceRegistry()
        mgr = ConversationManager()
        reg.register("conversation_manager", mgr)
        assert reg.get("conversation_manager") is reg.get("conversation_manager")

    def test_injected_into_ai_manager(self):
        reg = ServiceRegistry()
        conv_mgr = ConversationManager()
        tmpl_reg = PromptTemplateRegistry()

        reg.register("conversation_manager", conv_mgr)
        reg.register("template_registry", tmpl_reg)

        ai = AIManager(
            conversation_manager=conv_mgr,
            template_registry=tmpl_reg,
        )
        assert ai.conversation_manager is conv_mgr
        assert ai.template_registry is tmpl_reg

    def test_multiple_consumers_receive_same_tool_registry(self):
        reg = ServiceRegistry()
        tools = ToolRegistry()
        reg.register("tool_registry", tools)

        from_registry = reg.get("tool_registry")
        assert from_registry is tools


# ==========================================================================
# Lazy resolution
# ==========================================================================


class TestLazyResolution:
    """Services are resolved on demand from the registry."""

    def test_service_available_after_registration(self):
        reg = ServiceRegistry()
        assert reg.exists("ai_manager") is False
        reg.register("ai_manager", AIManager())
        assert reg.exists("ai_manager") is True


# ==========================================================================
# Optional services
# ==========================================================================


class TestOptionalServices:
    """Safe optional lookup for services that may not be registered."""

    def test_get_optional_returns_none_when_missing(self):
        reg = ServiceRegistry()
        assert reg.get_optional("nonexistent") is None

    def test_get_optional_returns_service_when_exists(self):
        reg = ServiceRegistry()
        reg.register("ai_manager", AIManager())
        assert reg.get_optional("ai_manager") is not None

    def test_get_optional_does_not_raise(self):
        reg = ServiceRegistry()
        result = reg.get_optional("missing_service")
        assert result is None  # no KeyError


# ==========================================================================
# Service replacement
# ==========================================================================


class TestServiceReplacement:
    """Registered services can be replaced after removal."""

    def test_remove_and_reregister(self):
        reg = ServiceRegistry()
        reg.register("ai_manager", AIManager())
        original = reg.get("ai_manager")
        reg.remove("ai_manager")
        replacement = AIManager()
        reg.register("ai_manager", replacement)
        assert reg.get("ai_manager") is not original
        assert reg.get("ai_manager") is replacement


# ==========================================================================
# Dependency resolution
# ==========================================================================


class TestDependencyResolution:
    """Services that depend on other services resolve through the registry."""

    def test_memory_aware_ai_depends_on_ai_manager(self):
        reg = ServiceRegistry()
        ai_mgr = AIManager()
        reg.register("ai_manager", ai_mgr)
        mem_ai = MemoryAwareAI(ai_manager=reg.get("ai_manager"))
        assert mem_ai._ai is ai_mgr

    def test_ai_manager_depends_on_conversation_manager(self):
        reg = ServiceRegistry()
        conv_mgr = ConversationManager()
        reg.register("conversation_manager", conv_mgr)
        ai = AIManager(conversation_manager=reg.get("conversation_manager"))
        assert ai.conversation_manager is conv_mgr


# ==========================================================================
# Metadata preservation
# ==========================================================================


class TestMetadataPreservation:
    """Service instances retain their state/metadata through the registry."""

    def test_conversation_manager_state_preserved(self):
        reg = ServiceRegistry()
        conv_mgr = ConversationManager()
        conv = conv_mgr.create(provider="test")
        reg.register("conversation_manager", conv_mgr)

        retrieved = reg.get("conversation_manager")
        assert retrieved.get(conv.conversation_id) is conv


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    """AIManager without injected services still works."""

    def test_ai_manager_default_construction(self):
        ai = AIManager()
        assert ai.router is not None
        assert ai.conversation_manager is not None
        assert ai.template_registry is not None

    def test_injection_overrides_defaults(self):
        custom_mgr = ConversationManager()
        ai = AIManager(conversation_manager=custom_mgr)
        assert ai.conversation_manager is custom_mgr

    def test_defaults_used_when_none_injected(self):
        ai = AIManager(conversation_manager=None, template_registry=None)
        assert ai.conversation_manager is not None
        assert ai.template_registry is not None


# ==========================================================================
# Service functionality
# ==========================================================================


class TestStructuredService:
    """StructuredService provides structured output parsing."""

    def test_parse_valid_json(self):
        svc = StructuredService()
        schema = StructuredSchema(name="test", schema={"type": "object"})
        result = svc.parse('{"key": "val"}', schema)
        assert result.valid is True
        assert result.data == {"key": "val"}

    def test_parse_invalid_json(self):
        svc = StructuredService()
        schema = StructuredSchema(name="test", schema={"type": "object"})
        result = svc.parse("not json", schema)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_schema(self):
        svc = StructuredService()
        schema = StructuredSchema(name="test", schema={"type": "object"})
        svc.validate(schema)  # no exception

    def test_create_schema(self):
        svc = StructuredService()
        schema = svc.create_schema("test", {"type": "object"})
        assert schema.name == "test"
        assert schema.schema == {"type": "object"}


class TestPlanningService:
    """PlanningService provides plan parsing and validation."""

    def test_parse_valid_plan(self):
        svc = PlanningService()
        plan = svc.parse(
            {"title": "t", "objective": "o", "steps": []},
            provider="test", model="m",
        )
        assert isinstance(plan, Plan)
        assert plan.title == "t"

    def test_validate_plan(self):
        svc = PlanningService()
        plan = svc.parse(
            {"title": "t", "objective": "o", "steps": [{"id": "s1", "title": "do"}]},
            provider="test", model="m",
        )
        result = svc.validate(plan)
        assert isinstance(result, PlanValidationResult)
        assert result.valid is True


class TestReasoningService:
    """ReasoningService provides reasoning chain parsing and validation."""

    def test_parse_valid_reasoning(self):
        svc = ReasoningService()
        chain = svc.parse(
            {"objective": "o", "steps": [{"id": "rs1", "title": "think", "action": "a", "result": "r"}], "conclusion": "c"},
            provider="test", model="m",
        )
        assert isinstance(chain, ReasoningChain)
        assert chain.objective == "o"

    def test_validate_reasoning(self):
        svc = ReasoningService()
        chain = svc.parse(
            {"objective": "o", "steps": [{"id": "rs1", "title": "think", "action": "a", "result": "r"}], "conclusion": "c"},
            provider="test", model="m",
        )
        result = svc.validate(chain)
        assert isinstance(result, ReasoningValidationResult)
        assert result.valid is True


# ==========================================================================
# Kernel registration pattern
# ==========================================================================


class TestKernelRegistrationPattern:
    """Verifies the registration pattern used in JarvisKernel.boot()."""

    def test_full_ai_service_wiring(self):
        reg = ServiceRegistry()

        _ai_router = AIRouter()
        _conv_manager = ConversationManager()
        _template_registry = PromptTemplateRegistry()
        _tool_registry = ToolRegistry()

        reg.register("ai_router", _ai_router)
        reg.register("conversation_manager", _conv_manager)
        reg.register("template_registry", _template_registry)
        reg.register("tool_registry", _tool_registry)

        reg.register(
            "ai_manager",
            AIManager(
                conversation_manager=_conv_manager,
                template_registry=_template_registry,
                router=_ai_router,
            ),
        )

        reg.register("structured_service", StructuredService())
        reg.register("planning_service", PlanningService())
        reg.register("reasoning_service", ReasoningService())

        mem_ai = MemoryAwareAI(
            ai_manager=reg.get("ai_manager"),
            memory_manager=reg.get_optional("memory"),
        )
        reg.register("memory_aware_ai", mem_ai)

        assert reg.exists("ai_router")
        assert reg.exists("conversation_manager")
        assert reg.exists("template_registry")
        assert reg.exists("tool_registry")
        assert reg.exists("ai_manager")
        assert reg.exists("structured_service")
        assert reg.exists("planning_service")
        assert reg.exists("reasoning_service")
        assert reg.exists("memory_aware_ai")
        assert reg.list_services() == sorted(reg.list_services())

        assert reg.get("ai_manager").conversation_manager is _conv_manager
        assert reg.get("ai_manager").template_registry is _template_registry
        assert isinstance(reg.get("structured_service"), StructuredService)
        assert isinstance(reg.get("planning_service"), PlanningService)
        assert isinstance(reg.get("reasoning_service"), ReasoningService)
        assert isinstance(reg.get("memory_aware_ai"), MemoryAwareAI)
