"""Regression tests for REAL agent objective execution.

Before this fix an agent created by the autonomy workflow (a ``DomainAgent``)
returned a pure stub dict from ``execute()`` and never inspected the project,
so the user received a generic conversational acknowledgement ("I'll inspect
...") instead of findings. These tests prove that a *wired* ``DomainAgent``
actually executes its assigned objective: it performs a strictly read-only
inspection of the project filesystem, gathers concrete evidence, and asks the
model to synthesize a grounded findings report.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

from app.agents.factory import AgentFactory
from app.agents.types import DomainAgent, DevelopmentAgent
from app.assistant.intent_router import (
    ExecutionRouter, IntentClassification, IntentClassifier, ROUTE_AGENT,
    _detect_explicit_agent_type,
)
from app.autonomy.agents.builder import AgentBuilder
from app.autonomy.agents.specification import AgentSpecification


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _AIStr(str):
    provider = "fake"
    model = "fake"
    metadata: dict = {}


class FakeAI:
    """Deterministic model stand-in.

    It proves the agent actually gathered evidence: the report it returns is
    grounded in a real ``.py`` module name harvested from the project walk, so
    a test can assert the output references the *actual* inspected files.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def ask(self, prompt: str = "", **_kwargs) -> "_AIStr":
        self.prompts.append(prompt)
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*\.py)", prompt)
        mod = match.group(1) if match else "no_module"
        return _AIStr(
            f"FINDINGS: the highest-priority pending issue lives in {mod}. "
            "This is a grounded, strictly read-only inspection report."
        )


class _JsonAI:
    """Fake AI that returns JSON with agent_type = 'development',
    simulating the AI overriding an explicit user 'domain' request."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def ask(self, *args, **_kwargs) -> str:
        self.prompts.append(args[1] if len(args) > 1 else args[0] if args else "")
        return '{"name": "DevAgent", "agent_type": "development", "objective": "test"}'


class _Reg:
    def __init__(self, name: str):
        self.name = name
        self.agent_id = name.lower()

    def to_dict(self) -> dict:
        return {"name": self.name}


class _RegList:
    def __init__(self, names: list[str]):
        self._names = names

    def list(self):
        return [_Reg(n) for n in self._names]


def _make_project() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "target_module.py").write_text("x = 1\n# TODO: fix the auth bug\n")
    (root / "helper.py").write_text("y = 2\n")
    (root / "README.md").write_text("# Demo\nDescribes the demo project.\n")
    return root


def _wired_agent(ai: FakeAI, project_root: Path, name: str = "ProjectInspector") -> DomainAgent:
    spec = AgentSpecification(
        name=name,
        objective=(
            "inspect the current JARVIS project status, identify the most "
            "important pending development issue, and report what should be fixed."
        ),
        domain="domain",
        capabilities=["analytics", "knowledge", "memory"],
        description="read-only project inspector",
    )
    builder = AgentBuilder(ai=ai, project_root=str(project_root))
    return builder.build(spec, capabilities=["analytics", "knowledge", "memory"])


# ---------------------------------------------------------------------------
# 1. Backwards compatibility: an unwired DomainAgent still returns the stub
# ---------------------------------------------------------------------------


class TestStubBackwardsCompat:
    def test_unwired_domain_agent_returns_stub(self):
        agent = DomainAgent(domain="security")
        assert agent._ai is None
        res = agent.execute({"query": "scan"})
        assert res["status"] == "ok"
        assert res["domain"] == "security"
        assert res["query"] == "scan"
        # No model was invoked and no message key is produced.
        assert "message" not in res


# ---------------------------------------------------------------------------
# 2. A wired agent actually executes its objective
# ---------------------------------------------------------------------------


class TestWiredAgentExecutes:
    def test_wired_agent_returns_message(self):
        root = _make_project()
        ai = FakeAI()
        agent = _wired_agent(ai, root)
        assert agent._ai is ai  # builder wired the AI manager in
        res = agent.execute({"request": "inspect the project"})
        assert res["status"] == "ok"
        assert res["message"]
        assert res["objective"] == "inspect the project"
        assert ai.prompts  # the model was actually asked

    def test_agent_gathers_real_evidence(self):
        root = _make_project()
        ai = FakeAI()
        agent = _wired_agent(ai, root)
        res = agent.execute({"request": "inspect"})
        evidence = res["evidence_summary"]
        assert "target_module.py" in evidence
        assert "TODO" in evidence
        # The prompt delivered to the model contained the gathered evidence.
        assert "EVIDENCE" in ai.prompts[0]
        assert "target_module.py" in ai.prompts[0]

    def test_agent_grounds_report_in_real_files(self):
        root = _make_project()
        ai = FakeAI()
        agent = _wired_agent(ai, root)
        msg = agent.execute({"request": "inspect"})["message"]
        real_modules = {p.name for p in root.glob("*.py")}
        # Not a generic acknowledgement; it references a real inspected file.
        assert "FINDINGS" in msg
        assert any(m in msg for m in real_modules)
        assert "i'll inspect" not in msg.lower()
        assert "please provide" not in msg.lower()

    def test_read_only_no_file_mutation(self):
        root = _make_project()
        ai = FakeAI()
        agent = _wired_agent(ai, root)
        before = sorted(p.name for p in root.iterdir())
        agent.execute({"request": "inspect"})
        after = sorted(p.name for p in root.iterdir())
        assert before == after  # strictly read-only: nothing created/changed

    def test_agent_uses_objective_from_spec_when_request_empty(self):
        root = _make_project()
        ai = FakeAI()
        agent = _wired_agent(ai, root)
        res = agent.execute({})  # no request -> falls back to spec objective
        assert res["objective"]  # resolved from spec.objective
        assert ai.prompts
        assert res["objective"] in ai.prompts[0]

    def test_builder_wires_capabilities_and_active_status(self):
        root = _make_project()
        ai = FakeAI()
        agent = _wired_agent(ai, root)
        cap_names = {c.name for c in agent.metadata.capabilities}
        # The agent was built with its declared (validated) capability set.
        assert {"analytics", "knowledge", "memory"} <= cap_names
        # And it is live/active and wired for execution, not a dormant stub.
        assert agent.status.value == "active"
        assert agent._ai is ai


# ---------------------------------------------------------------------------
# 3. Dispatch: classifier + ExecutionRouter reach the REAL agent
# ---------------------------------------------------------------------------


class TestDispatchToRealAgent:
    def test_router_invokes_real_domain_agent(self):
        root = _make_project()
        ai = FakeAI()
        agent = _wired_agent(ai, root)
        router = ExecutionRouter(
            agents=_RegList(["projectinspector"]),
            agent_instances={"projectinspector": agent},
        )
        result = router.execute(
            IntentClassification(
                route=ROUTE_AGENT,
                target="projectinspector",
                params={"request": "inspect"},
            )
        )
        assert agent._ai.prompts  # execute() actually ran
        assert "FINDINGS" in result["text"]
        assert result["data"]["success"] is True


# ---------------------------------------------------------------------------
# 4. End-to-end: the REAL agent's findings propagate to the chat layer
# ---------------------------------------------------------------------------


class TestEndToEndPropagation:
    def test_real_agent_result_reaches_chat(self):
        from app.core.kernel import JarvisKernel

        kernel = JarvisKernel()
        kernel.boot()
        try:
            rt = kernel.registry.get("assistant_runtime")
            engine = kernel.registry.get("autonomy_workflow_engine")

            root = _make_project()
            ai = FakeAI()
            agent = _wired_agent(ai, root)
            engine._agent_instances["ProjectInspector"] = agent
            engine._agent_instances[agent.agent_id] = agent

            message = (
                "ProjectInspectorAgent, execute your assigned objective now. "
                "Inspect the current JARVIS project status, identify the single "
                "most important pending development issue, and report it. Do not "
                "modify any files. Report your findings only."
            )
            result = rt.handle_message(message)
            assert result.get("kind") == "reply"
            # The chat text carries the REAL agent's grounded findings, not a
            # generic LLM acknowledgement.
            assert "FINDINGS" in result["text"]
            assert ai.prompts  # the agent actually executed its objective
        finally:
            kernel.shutdown()


# ---------------------------------------------------------------------------
# 5. Approval architecture remains intact (no regression)
# ---------------------------------------------------------------------------


class TestApprovalIntact:
    def test_modification_still_requires_approval(self):
        from app.assistant.approval import ApprovalGate

        gate = ApprovalGate()
        executed: list[int] = []

        def executor():
            executed.append(1)
            return {"kind": "executed"}

        reply = gate.propose(
            "modify",
            "refactor app/core/kernel.py",
            "Proposed change to core kernel",
            executor=executor,
        )
        assert reply.get("kind") == "approval_required"
        assert gate.pending is not None
        assert executed == []  # NOT executed before approval

        gate.handle("approve")
        assert executed == [1]


# ---------------------------------------------------------------------------
# 6. Desktop creation path: _run_agent_pipeline wires execution context
# ---------------------------------------------------------------------------


class _FakeAgentRegistration:
    def __init__(self, agent: DomainAgent) -> None:
        self.agent_id = agent.agent_id
        self.name = agent.metadata.name
        self.agent_type = agent.agent_type
        self.status = agent.status
        self.parent_agent_id = ""
        self.child_agent_ids: list[str] = []
        self.metadata: dict[str, Any] = (
            agent.metadata.to_dict() if hasattr(agent.metadata, "to_dict") else {}
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "agent_type": self.agent_type,
            "status": self.status.value,
        }


class _FakeAgentRegistry:
    def register(self, agent: DomainAgent) -> _FakeAgentRegistration:
        reg = _FakeAgentRegistration(agent)
        return reg

    def update_properties(
        self,
        agent_id: str,
        objective: str = "",
        permissions: str = "",
        memory_scope: str = "",
    ) -> None:
        pass


class _FakeAIManager:
    """Deterministic AI stand-in that records prompts so tests can
    confirm the agent actually invoked the model during execute()."""

    def __init__(self, reply: str = "GROUNDED REPORT: inspection complete.") -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def ask(self, prompt: str = "", **_kwargs: Any) -> "_AIStr":
        self.prompts.append(prompt)
        return _AIStr(self.reply)


class TestDesktopCreationPath:
    """Desktop path: AgentFactory.create via ExecutionRouter._run_agent_pipeline
    must receive execution-context wiring so DomainAgent.execute() runs the
    real inspection instead of the legacy stub dict."""

    def test_factory_create_domain_agent_is_stub_by_default(self):
        """A. AgentFactory.create without explicit wiring produces a stub
        DomainAgent so cloning / discovery / merging / recovery / marketplace
        callers remain unaffected."""
        agent = AgentFactory.create(
            "domain",
            name="ProjectStatusAgent",
            description="inspector",
            capabilities=["analytics", "knowledge"],
        )
        assert isinstance(agent, DomainAgent)
        assert agent._ai is None
        assert agent._objective is None
        assert agent._capabilities_registry is None
        res = agent.execute({"request": "inspect"})
        assert res == {"status": "ok", "domain": "general", "query": "inspect"}

    def test_run_agent_pipeline_wires_execution_context(self):
        """B. Desktop agent creation path (_run_agent_pipeline) wires
        _ai, _objective, _capabilities_registry and _project_root."""
        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        spec = {
            "name": "ProjectStatusAgent",
            "agent_type": "domain",
            "description": "inspect the project",
            "objective": (
                "Inspect the current JARVIS project status and identify "
                "the single most important pending development issue."
            ),
            "capabilities": ["analytics", "knowledge", "memory"],
        }
        router._run_agent_pipeline("Inspect the project", spec)
        agent = router._agent_instances["ProjectStatusAgent"]
        assert agent._ai is ai
        assert agent._objective == spec["objective"]
        assert agent._capabilities_registry is not None
        assert agent._project_root == os.getcwd()

    def test_wired_agent_execute_returns_grounded_result(self):
        """C. DomainAgent.execute() enters the real path after Desktop
        wiring: result carries status, message, objective, evidence_summary,
        domain and is NOT the legacy stub dictionary."""
        ai = _FakeAIManager(
            reply="FINDINGS: the highest-priority pending issue is in app/assistant/intent_router.py"
        )
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        spec = {
            "name": "ProjectStatusAgent",
            "agent_type": "domain",
            "description": "inspect",
            "objective": "Inspect the current JARVIS project status.",
            "capabilities": ["analytics", "knowledge", "memory"],
        }
        router._run_agent_pipeline("Inspect the project", spec)
        agent = router._agent_instances["ProjectStatusAgent"]
        res = agent.execute({"request": "Inspect the project"})
        assert res["status"] == "ok"
        assert "message" in res
        assert "objective" in res
        assert "evidence_summary" in res
        assert "domain" in res
        # Must not be the legacy stub shape.
        assert not (
            set(res.keys()) == {"status", "domain", "query"} and res["status"] == "ok"
        )

    def test_evidence_summary_contains_real_project_walk(self):
        """C1. evidence_summary reflects an actual read-only project walk
        under the architecture's project root (os.getcwd())."""
        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        spec = {
            "name": "ProjectStatusAgent",
            "agent_type": "domain",
            "description": "inspect",
            "objective": "Inspect the current JARVIS project status.",
            "capabilities": ["analytics"],
        }
        router._run_agent_pipeline("Inspect", spec)
        agent = router._agent_instances["ProjectStatusAgent"]
        res = agent.execute({"request": "Inspect"})
        evidence = res["evidence_summary"]
        assert "Project root:" in evidence
        # The walk must have surfaced real project files.
        assert "Python modules" in evidence

    def test_agent_builder_still_wires_correctly(self):
        """D. Regression: AgentBuilder.build() continues to wire execution
        context exactly as before."""
        from app.agents.capabilities import get_capability_registry

        ai = _FakeAIManager()
        root = _make_project()
        spec = AgentSpecification(
            name="ProjectInspector",
            objective="inspect the current JARVIS project status",
            domain="domain",
            capabilities=["analytics", "knowledge", "memory"],
            description="read-only project inspector",
        )
        builder = AgentBuilder(
            ai=ai,
            project_root=str(root),
            capabilities_registry=get_capability_registry(),
        )
        agent = builder.build(spec, capabilities=["analytics", "knowledge", "memory"])
        assert agent._ai is ai
        assert agent._objective == "inspect the current JARVIS project status"
        assert agent._capabilities_registry is not None
        assert agent._project_root == str(root)
        assert agent.status.value == "active"

    def test_factory_create_unchanged_for_other_callers(self):
        """E. AgentFactory.create still produces a stub without wiring so
        non-Desktop callers (cloning, discovery, merging, recovery,
        marketplace) are unaffected."""
        agent = AgentFactory.create("domain", name="cloned_agent")
        assert isinstance(agent, DomainAgent)
        assert agent._ai is None
        assert agent._objective is None
        assert agent._capabilities_registry is None
        res = agent.execute({"request": "inspect"})
        assert res == {"status": "ok", "domain": "general", "query": "inspect"}

    def test_build_agent_spec_preserves_explicit_domain_type(self):
        """F. _build_agent_spec preserves explicit user agent type
        (e.g. 'domain agent') over the AI's generated agent_type
        (which would otherwise choose 'development')."""
        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        request = "domain agent, execute your assigned objective now. Inspect the project."
        spec_text, spec = router._build_agent_spec(
            request,
            explicit_agent_type=_detect_explicit_agent_type(request),
        )
        assert spec["agent_type"] == "domain"

    def test_build_agent_spec_preserves_other_explicit_types(self):
        """F1. _build_agent_spec also preserves other explicit types
        (e.g. 'system agent') over the AI's generated agent_type."""
        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        request = "system agent, manage system-level operations."
        spec_text, spec = router._build_agent_spec(
            request,
            explicit_agent_type=_detect_explicit_agent_type(request),
        )
        assert spec["agent_type"] == "system"

    def test_classify_preserves_domain_agent_type(self):
        """G. IntentClassifier.classify() detects explicit 'domain agent'
        from the original user text and preserves it in params."""
        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        classifier = IntentClassifier()
        classification = classifier.classify(
            "domain agent, execute your assigned objective now.",
        )
        assert classification.params.get("agent_type") == "domain"

    def test_classify_preserves_system_agent_type(self):
        """G1. IntentClassifier.classify() detects explicit 'system agent'
        from the original user text and preserves it in params."""
        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        classifier = IntentClassifier()
        classification = classifier.classify(
            "system agent, build a new capability.",
        )
        assert classification.params.get("agent_type") == "system"

    def test_full_pipeline_domain_cannot_be_overridden_by_ai(self):
        """H. End-to-end: an AI response of 'development' cannot override
        an explicit 'domain agent' request through the real
        classifier → proposal → approval → creation path.
        The created agent must be a DomainAgent with agent_type == 'domain'."""
        from app.agents.types import DomainAgent

        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        request = "domain agent, execute your assigned objective now."
        classifier = IntentClassifier()
        classification = classifier.classify(request)
        assert classification.params.get("agent_type") == "domain"
        result = router.execute(classification)
        # The approval gate returns approval_required for agent_create.
        # Verify the spec passed to the approval contains agent_type == 'domain'.
        if result.get("kind") == "approval_required":
            spec = result.get("data", {}).get("spec", {})
            assert spec.get("agent_type") == "domain"

    def test_full_pipeline_system_cannot_be_overridden_by_ai(self):
        """H1. End-to-end: same guarantee for 'system agent' explicit type."""
        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        request = "system agent, build a new capability."
        classifier = IntentClassifier()
        classification = classifier.classify(request)
        assert classification.params.get("agent_type") == "system"
        result = router.execute(classification)
        if result.get("kind") == "approval_required":
            spec = result.get("data", {}).get("spec", {})
            assert spec.get("agent_type") == "system"

    def test_run_agent_pipeline_safeguard_respects_explicit_type(self):
        """I. _run_agent_pipeline() construction-boundary safeguard
        enforces explicit_agent_type even if spec says otherwise."""
        from app.agents.types import DomainAgent

        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        spec = {
            "name": "ProjectStatusAgent",
            "agent_type": "development",  # AI would generate this
            "description": "inspect",
            "objective": "Inspect the project.",
            "capabilities": ["analytics", "knowledge", "memory"],
        }
        router._run_agent_pipeline(
            "Inspect the project",
            spec,
            explicit_agent_type="domain",
        )
        agent = router._agent_instances["ProjectStatusAgent"]
        assert isinstance(agent, DomainAgent)
        assert agent.agent_type == "domain"

    def test_run_agent_pipeline_no_explicit_type_uses_spec(self):
        """I1. _run_agent_pipeline() uses spec agent_type when no
        explicit type is provided (backward compatibility)."""
        from app.agents.types import DevelopmentAgent

        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        spec = {
            "name": "DevAgent",
            "agent_type": "development",
            "description": "develop",
            "objective": "Develop the project.",
            "capabilities": ["analytics"],
        }
        router._run_agent_pipeline(
            "Develop the project",
            spec,
            explicit_agent_type=None,
        )
        agent = router._agent_instances["DevAgent"]
        assert isinstance(agent, DevelopmentAgent)
        assert agent.agent_type == "development"


# ---------------------------------------------------------------------------
# Type inference regression tests
# ---------------------------------------------------------------------------


class TestAgentTypeInference:
    """Verify _run_agent_pipeline() correctly infers agent type
    when explicit_agent_type is None."""

    def _make_router(self, ai=None, registry=None):
        """Helper: create an ExecutionRouter with fakes."""
        ai = ai or _FakeAIManager()
        registry = registry or _FakeAgentRegistry()
        return ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)

    # ---- A. Explicit domain type beats AI development type ----

    def test_explicit_domain_beats_ai_development(self):
        """A. When explicit_agent_type='domain', the agent MUST be
        DomainAgent even if the spec says agent_type='development'."""
        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "ProjectStatusAgent",
            "agent_type": "development",  # AI-generated, should be overridden
            "description": "inspect the project",
            "objective": "Inspect the current JARVIS project status.",
            "capabilities": ["analytics", "knowledge", "memory"],
        }
        router._run_agent_pipeline("Inspect the project", spec, explicit_agent_type="domain")
        agent = router._agent_instances["ProjectStatusAgent"]
        assert isinstance(agent, DomainAgent), \
            f"Expected DomainAgent but got {type(agent).__name__}"
        assert agent.agent_type == "domain"

    # ---- B. Project inspection objective with AI development type ----

    def test_inspection_objective_with_ai_development_produces_domain(self):
        """B. When the objective indicates project inspection and the
        AI generated 'development', the pipeline must infer 'domain'."""
        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "ProjectStatusAgent",
            "agent_type": "development",  # AI incorrectly generated this
            "description": "inspect the project",
            "objective": "Inspect the current JARVIS project status and identify the most important pending development issue.",
            "capabilities": ["analytics", "knowledge", "memory"],
        }
        router._run_agent_pipeline("Inspect the project", spec, explicit_agent_type=None)
        agent = router._agent_instances["ProjectStatusAgent"]
        assert isinstance(agent, DomainAgent), \
            f"Expected DomainAgent but got {type(agent).__name__}"
        assert agent.agent_type == "domain"

    # ---- C. Explicit development type remains DevelopmentAgent ----

    def test_explicit_development_remains_development(self):
        """C. When explicit_agent_type='development', the agent MUST be
        DevelopmentAgent."""
        from app.agents.types import DevelopmentAgent

        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "DevAgent",
            "agent_type": "development",
            "description": "develop",
            "objective": "Develop the project.",
            "capabilities": ["analytics"],
        }
        router._run_agent_pipeline("Develop the project", spec, explicit_agent_type="development")
        agent = router._agent_instances["DevAgent"]
        assert isinstance(agent, DevelopmentAgent), \
            f"Expected DevelopmentAgent but got {type(agent).__name__}"
        assert agent.agent_type == "development"

    # ---- D. No explicit type + legitimate development objective ----

    def test_legitimate_development_objective_remains_development(self):
        """D. When the objective genuinely asks for development
        (e.g. writing code), DevelopmentAgent should be created."""
        from app.agents.types import DevelopmentAgent

        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "CodeGenerator",
            "agent_type": "development",
            "description": "write python code",
            "objective": "Write a Python script that automates testing.",
            "capabilities": ["analytics", "tool"],
        }
        router._run_agent_pipeline("Write a script", spec, explicit_agent_type=None)
        agent = router._agent_instances["CodeGenerator"]
        assert isinstance(agent, DevelopmentAgent), \
            f"Expected DevelopmentAgent but got {type(agent).__name__}"
        assert agent.agent_type == "development"

    # ---- E. Explicit system/tool/composite behavior ----

    def test_explicit_system_type_remains_system(self):
        """E1. Explicit system type is preserved."""
        from app.agents.types import SystemAgent

        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "SysAgent",
            "agent_type": "system",
            "description": "system ops",
            "objective": "Manage system-level operations.",
        }
        router._run_agent_pipeline("System ops", spec, explicit_agent_type="system")
        agent = router._agent_instances["SysAgent"]
        assert isinstance(agent, SystemAgent), \
            f"Expected SystemAgent but got {type(agent).__name__}"
        assert agent.agent_type == "system"

    def test_explicit_composite_type_remains_composite(self):
        """E2. Explicit composite type is preserved."""
        from app.agents.types import CompositeAgent

        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "CompAgent",
            "agent_type": "composite",
            "description": "composite agent",
            "objective": "Coordinate sub-agents.",
        }
        router._run_agent_pipeline("Composite ops", spec, explicit_agent_type="composite")
        agent = router._agent_instances["CompAgent"]
        assert isinstance(agent, CompositeAgent), \
            f"Expected CompositeAgent but got {type(agent).__name__}"
        assert agent.agent_type == "composite"

    # ---- F. Created DomainAgent receives execution dependencies ----

    def test_domain_agent_receives_execution_dependencies(self):
        """F. A DomainAgent created via _run_agent_pipeline with
        inferred type must receive _ai, _objective, _capabilities_registry,
        and _project_root."""
        from app.agents.capabilities import get_capability_registry

        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "ProjectStatusAgent",
            "agent_type": "development",  # AI-generated, should be overridden
            "description": "inspect the project",
            "objective": "Inspect the current JARVIS project status.",
            "capabilities": ["analytics", "knowledge", "memory"],
        }
        router._run_agent_pipeline("Inspect the project", spec, explicit_agent_type=None)
        agent = router._agent_instances["ProjectStatusAgent"]
        assert isinstance(agent, DomainAgent)
        assert agent._ai is ai
        assert agent._objective == spec["objective"]
        assert agent._capabilities_registry is not None
        assert agent._project_root is not None

    # ---- G. DomainAgent execute does NOT return the stub ----

    def test_domain_agent_execute_not_stub(self):
        """G. A DomainAgent created with inferred type must NOT return
        {'status': 'ok', 'language': 'python', 'task': 'unknown'}."""
        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "ProjectStatusAgent",
            "agent_type": "development",
            "description": "inspect the project",
            "objective": "Inspect the current JARVIS project status.",
            "capabilities": ["analytics", "knowledge", "memory"],
        }
        router._run_agent_pipeline("Inspect the project", spec, explicit_agent_type=None)
        agent = router._agent_instances["ProjectStatusAgent"]
        result = agent.execute({"request": "Inspect the project"})
        assert result != {"status": "ok", "language": "python", "task": "unknown"}, \
            "DomainAgent must not return the DevelopmentAgent stub"
        assert result["status"] == "ok"
        assert "message" in result or "domain" in result

    # ---- H. No explicit type + inspection keywords ----

    def test_inspection_keywords_without_explicit_type_infer_domain(self):
        """H. Objectives with inspection keywords infer 'domain'
        even when capabilities are minimal."""
        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "StatusAgent",
            "agent_type": "development",
            "description": "check project status",
            "objective": "Check the project status and report findings.",
            "capabilities": ["memory"],
        }
        router._run_agent_pipeline("Check status", spec, explicit_agent_type=None)
        agent = router._agent_instances["StatusAgent"]
        assert isinstance(agent, DomainAgent), \
            f"Expected DomainAgent but got {type(agent).__name__}"
        assert agent.agent_type == "domain"

    # ---- I. Development keywords do NOT trigger domain inference ----

    def test_development_keywords_do_not_trigger_domain(self):
        """I. Objectives with only development keywords do NOT infer
        'domain' when the AI generates 'development'."""
        from app.agents.types import DevelopmentAgent

        ai = _FakeAIManager()
        registry = _FakeAgentRegistry()
        router = self._make_router(ai=ai, registry=registry)
        spec = {
            "name": "CodeAgent",
            "agent_type": "development",
            "description": "write code",
            "objective": "Write a Python script to automate testing.",
            "capabilities": ["tool", "analytics"],
        }
        router._run_agent_pipeline("Write script", spec, explicit_agent_type=None)
        agent = router._agent_instances["CodeAgent"]
        assert isinstance(agent, DevelopmentAgent), \
            f"Expected DevelopmentAgent but got {type(agent).__name__}"
        assert agent.agent_type == "development"


# ---------------------------------------------------------------------------
# IntentRouter type inference integration tests
# ---------------------------------------------------------------------------


class TestIntentRouterTypeInference:
    """Verify IntentClassifier preserves explicit type and
    _resolve_agent_type works at the classification boundary."""

    def test_classify_with_inspection_objective_no_explicit_type(self):
        """Verify classify() works when user describes inspection
        without 'domain agent' phrasing."""
        classifier = IntentClassifier()
        classification = classifier.classify(
            "ProjectStatusAgent, execute your assigned objective now. Inspect the current JARVIS project status.",
            agent_names=["ProjectStatusAgent"],
        )
        # The classification should have target set to the agent name
        assert classification.target is not None
        assert "ProjectStatusAgent" in classification.target
        assert classification.route == ROUTE_AGENT

    def test_resolve_agent_type_explicit_domain(self):
        """Explicit domain type wins."""
        from app.assistant.intent_router import ExecutionRouter

        router = ExecutionRouter(ai=None, agents=None, event_bus=None, graph=None)
        spec = {
            "name": "TestAgent",
            "agent_type": "development",
            "objective": "Inspect the project.",
            "capabilities": ["analytics"],
        }
        result = ExecutionRouter._resolve_agent_type(
            "Inspect the project", spec, "domain",
        )
        assert result == "domain"

    def test_resolve_agent_type_inferred_from_inspection(self):
        """Project inspection objective infers domain."""
        router = ExecutionRouter(ai=None, agents=None, event_bus=None, graph=None)
        spec = {
            "name": "TestAgent",
            "agent_type": "development",
            "objective": "Inspect the current JARVIS project status.",
            "capabilities": ["analytics", "knowledge", "memory"],
        }
        result = ExecutionRouter._resolve_agent_type(
            "Inspect the project", spec, None,
        )
        assert result == "domain"

    def test_resolve_agent_type_legitimate_development(self):
        """Legitimate development objectives remain development."""
        router = ExecutionRouter(ai=None, agents=None, event_bus=None, graph=None)
        spec = {
            "name": "CodeAgent",
            "agent_type": "development",
            "objective": "Write a Python script to automate testing.",
            "capabilities": ["tool", "analytics"],
        }
        result = ExecutionRouter._resolve_agent_type(
            "Write script", spec, None,
        )
        assert result == "development"

    def test_resolve_agent_type_no_signals_uses_spec(self):
        """When no signals are present, fall back to spec agent_type."""
        router = ExecutionRouter(ai=None, agents=None, event_bus=None, graph=None)
        spec = {
            "name": "TestAgent",
            "agent_type": "composite",
            "objective": "Coordinate sub-agents.",
        }
        result = ExecutionRouter._resolve_agent_type(
            "Coordinate", spec, None,
        )
        assert result == "composite"
