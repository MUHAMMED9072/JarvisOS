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
from app.agents.types import DomainAgent
from app.assistant.intent_router import ExecutionRouter, IntentClassification, ROUTE_AGENT
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
        spec_text, spec = router._build_agent_spec(request)
        assert spec["agent_type"] == "domain"

    def test_build_agent_spec_preserves_other_explicit_types(self):
        """F1. _build_agent_spec also preserves other explicit types
        (e.g. 'system agent') over the AI's generated agent_type."""
        ai = _JsonAI()
        registry = _FakeAgentRegistry()
        router = ExecutionRouter(ai=ai, agents=registry, event_bus=None, graph=None)
        request = "system agent, manage system-level operations."
        spec_text, spec = router._build_agent_spec(request)
        assert spec["agent_type"] == "system"
