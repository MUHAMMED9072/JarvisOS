# JARVIS OS Next-Generation Architecture

## Current State Assessment

| Domain | Status |
|--------|--------|
| EventBus / Messaging | Complete (`app/core/event_bus.py`) |
| ServiceRegistry / DI | Complete (`app/core/registry.py`) |
| AI Providers & Routing | Complete (`app/ai/providers/`, `app/ai/router.py`) |
| Plugin System | Complete (lifecycle, security, packaging, scaffolding) |
| Skill System | Complete (management, generation, installation, templates) |
| Evolution Engine | Complete (plan, generate, sandbox, test, approve, install) |
| Memory (base) | Functional (JSON-file backed, session, history) |
| Memory (advanced) | Stubs only (knowledge, search, preferences, context, projects) |
| REST API | Complete (health, AI, skills, plugins, evolution, memory, voice, WS) |
| WebSocket | Complete (streaming, commands, auth, reliability, admin, metrics) |
| Desktop Client | Complete (UI framework with 5 views) |
| **Agent System** | **DOES NOT EXIST** |
| **Agent Registry** | **DOES NOT EXIST** |
| **Agent Factory** | **DOES NOT EXIST** |
| **Scheduler** | **DOES NOT EXIST** |
| **Goal Engine** | **Partial** (only in evolution) |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        User Goal                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    Supervisor                                │
│  Orchestrates goal decomposition across agents              │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                     Planner                                 │
│  Breaks goals into tasks, produces directed acyclic graph   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  Agent Manager                              │
│  Evaluates tasks → checks Agent Registry → routes to        │
│  existing agent OR spawns new agent via Agent Factory       │
└──────────┬───────────────────────────────────┬──────────────┘
           │                                   │
           ▼                                   ▼
┌──────────────────────┐    ┌──────────────────────────────────┐
│   Agent Registry     │    │         Agent Factory            │
│  - Active agents     │    │  1. Capability Analysis          │
│  - Agent versions    │    │  2. Gap Detection                │
│  - Agent metadata    │    │  3. Spec Generation              │
│  - Agent health      │    │  4. Code Generation              │
│  - Agent discovery   │    │  5. Unit Tests                   │
│                      │    │  6. Integration Tests            │
│  Reuse if exists ────┼───→│  7. Sandbox Execution            │
│                      │    │  8. Benchmarking                 │
│                      │    │  9. Review                       │
│                      │    │ 10. Human Approval               │
│                      │    │ 11. Installation                 │
│                      │    │ 12. Registration                 │
└──────────────────────┘    └──────────────────────────────────┘
           │                                   │
           └───────────────┬───────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Agent Instance                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Agent Memory │  │Skills/Tools  │  │ Communication    │   │
│  │ - Episodic   │  │ - Registered │  │ - Agent-to-Agent│   │
│  │ - Semantic   │  │ - Discovered │  │ - Agent-to-User │   │
│  │ - Procedural │  │ - Generated  │  │ - Agent-to-Sys  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Metrics      │  │ Health       │  │ Versioning       │   │
│  │ - Perf stats │  │ - Heartbeat  │  │ - SemVer         │   │
│  │ - Success%   │  │ - Liveness   │  │ - Changelog      │   │
│  │ - Latency    │  │ - Readiness  │  │ - Rollback       │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Verification & Learning                     │
│  Test → Benchmark → Review → Approve → Install → Learn     │
└─────────────────────────────────────────────────────────────┘
```

---

## Dependency Graph

```
Phase 1 (AI Kernel)
  ├── Phase 2 (Goal Engine) ──┐
  │                           ├── Phase 4 (Agent Framework)
  ├── Phase 3 (Tool Layer) ───┘           │
  │                                       ├── Phase 5 (Agent Factory)
  │                                       │       │
  │                                       │       ├── Phase 6 (Marketplace)
  │                                       │       │
  │                                       │       └── Phase 7 (Long-term Learning)
  │                                       │               │
  │                                       │               └── Phase 8 (Self-Evolution)
  │                                       │                       │
  │                                       └── Phase 9 (Multi-Model) ── Phase 10 (Autonomous)
```

Edges: Phase N → Phase M means Phase N must be complete before Phase M begins.

---

## Phase 1 — AI Kernel (Build on existing)

**Goal**: Formalize the foundational infrastructure that agents depend on.

**What exists**: EventBus (complete), ServiceRegistry (complete), Config (complete), AI providers (complete)

**What to build**:

### 1.1 Scheduler (`app/kernel/scheduler.py`)
- `Task` dataclass: id, coro, priority, schedule (cron/interval/once), max_retries, timeout
- `Scheduler` class: task queue (heapq), thread pool executor, cron expression parser
- `ScheduledTask` wrapper: next_run, last_run, run_count, failure_count, status
- Methods: `schedule()`, `unschedule()`, `pause()`, `resume()`, `list()`, `list_due()`, `run_due()`
- Thread-safe with `asyncio.locks` or `threading.Lock`
- Integration with EventBus: publish `scheduler.task.completed`, `scheduler.task.failed`, `scheduler.task.scheduled`

### 1.2 Agent Registry Foundation (`app/agents/registry.py`)
- `AgentMetadata` dataclass: agent_id, name, version, description, capabilities, dependencies, status, created_at, updated_at
- `AgentRegistry` class: register, unregister, get, list, search (by capability, name, status)
- Backed by JSON file storage (reuse `MemoryStorage` pattern)
- Publish registry events on EventBus

### 1.3 Security Layer Enhancement (`app/kernel/security/`)
- Extend Plugin SDK's `PermissionManager` to kernel level
- `AgentPermission` model: agent_id, permissions (list of Permission), granted_by, granted_at, expires_at
- `SecurityContext` for request-scoped auth checks
- Resource quotas per agent (CPU, RAM, network, storage, API calls/min)

### 1.4 Memory Enhancement — Foundation (`app/memory/`)
- Fill `knowledge.py` stub: `KnowledgeBase` with chunking, embedding, and similarity search
- Fill `search.py` stub: `SemanticSearch` with embedding providers
- `VectorMemory` — lightweight vector storage using NumPy (no external vector DB dependency)
- `HybridMemory` — combine keyword + vector search

**Success criteria**:
- [ ] Scheduler can run 1000+ scheduled tasks
- [ ] Agent Registry can register/list/search agents by capability
- [ ] Security layer blocks unauthorized agent operations
- [ ] Memory can store/retrieve vectors, KNN search < 100ms on 10K vectors
- [ ] All components publish/receive events correctly

**Key files**:
- `app/kernel/scheduler.py` (NEW)
- `app/agents/registry.py` (NEW)
- `app/kernel/security/` (NEW)
- `app/memory/knowledge.py` (fill stub)
- `app/memory/search.py` (fill stub)

---

## Phase 2 — Goal Engine

**Goal**: Enable JARVIS to decompose complex user goals into actionable tasks, reason about them, and select optimal strategies.

**What exists**: `AIManager.plan()` and `AIManager.reason()` methods, `EvolutionPlanner`

**What to build**:

### 2.1 Goal Model (`app/goals/models.py`)
- `Goal` dataclass: id, description, priority, deadline, status (pending/active/completed/failed), parent_goal_id, sub_goals, metadata
- `GoalState` enum: PENDING, ACTIVE, BLOCKED, COMPLETED, FAILED, CANCELLED
- `Task` dataclass: id, goal_id, description, agent_requirements, estimated_effort, dependencies
- `TaskGraph` — DAG of tasks with topological ordering

### 2.2 Goal Planner (`app/goals/planner.py`)
- `GoalPlanner` class: takes Goal → produces TaskGraph
- AI-driven decomposition: uses `AIManager.plan()` to break goal into sub-goals and tasks
- Dependency resolution: topological sort + critical path analysis
- Resource estimation: AI estimates compute/memory/time per task
- `Plan` dataclass: tasks, dependencies, estimated_duration, confidence_score

### 2.3 Reasoner (`app/goals/reasoner.py`)
- `Reasoner` class: evaluates alternatives, produces justifications
- Methods: `evaluate_approach()`, `compare_strategies()`, `validate_plan()`
- Uses `AIManager.reason()` with structured prompts
- `ReasoningChain` — list of reasoning steps with evidence

### 2.4 Reflection Engine (`app/goals/reflection.py`)
- `ReflectionEngine` class: post-execution analysis
- Methods: `analyze_outcome()`, `identify_improvements()`, `update_heuristics()`
- Success/failure pattern recognition across goal executions
- Feedback loop to Planner for future improvements

### 2.5 Decision Engine (`app/goals/decision.py`)
- `DecisionEngine` class: choose between competing agents, strategies, plans
- `DecisionMatrix` — weighted scoring with criteria
- `Decision` dataclass: choice, rationale, confidence, alternatives
- Integration with Reasoner for justification

**Success criteria**:
- [ ] "Build a trading bot" → decomposed into 5-15 actionable tasks
- [ ] TaskGraph correctly handles dependencies and parallelism
- [ ] Reasoner produces coherent justifications for decisions
- [ ] Reflection identifies root causes of failures
- [ ] Decision engine selects optimal agent/tool for each task >80% accuracy

**Key files**:
- `app/goals/models.py` (NEW)
- `app/goals/planner.py` (NEW)
- `app/goals/reasoner.py` (NEW)
- `app/goals/reflection.py` (NEW)
- `app/goals/decision.py` (NEW)

---

## Phase 3 — Universal Tool Layer

**Goal**: Provide every agent with a rich, secure, uniform tool library.

**What exists**: `ToolDefinition`, `ToolRegistry`, `ToolCall`, `ToolResult` — general framework but few implementations.

**What to build**:

### 3.1 Tool Implementations (`app/tools/`)
Each tool is a class with `name`, `description`, `parameters` (JSON Schema), and `execute(params) -> ToolResult`.

| Tool | File | Description |
|------|------|-------------|
| `PythonTool` | `app/tools/python.py` | Execute Python code (sandboxed via `Sandbox`) |
| `ShellTool` | `app/tools/shell.py` | Execute shell commands (sandboxed) |
| `GitTool` | `app/tools/git.py` | Git operations (clone, commit, push, branch, merge) |
| `FileTool` | `app/tools/file.py` | File read/write/copy/move/delete with path safety |
| `RESTTool` | `app/tools/rest.py` | HTTP requests (GET, POST, PUT, DELETE, PATCH) |
| `BrowserTool` | `app/tools/browser.py` | Web scraping, search (reuse `BrowserSearchSkill`) |
| `DatabaseTool` | `app/tools/database.py` | SQL query execution (abstracted, SQLite first) |
| `DockerTool` | `app/tools/docker.py` | Docker container management |
| `OfficeTool` | `app/tools/office.py` | Document generation (PDF, Markdown, HTML) |
| `CloudTool` | `app/tools/cloud.py` | Cloud API adapters (extensible) |

### 3.2 Tool Security (`app/tools/security.py`)
- Per-tool permission requirements (maps to Plugin SDK `Permission` model)
- `ToolSecurityPolicy`: allow/deny lists, rate limits, resource quotas
- `ToolAuditLog`: every tool call logged with agent_id, params, result, duration

### 3.3 Tool Discovery & Registration
- Tools auto-register with `ToolRegistry` on import
- `@tool` decorator for simple tool definitions
- `ToolSuite` — composable groups of related tools

**Success criteria**:
- [ ] 10+ tool implementations pass unit tests
- [ ] All tools enforce security policies
- [ ] Tools can be composed together
- [ ] Tool audit log captures every invocation
- [ ] Browser tool can search the web and extract content
- [ ] Python tool executes sandboxed code with timeout

**Key files**:
- `app/tools/python.py` (NEW)
- `app/tools/shell.py` (NEW)
- `app/tools/git.py` (NEW)
- `app/tools/file.py` (NEW)
- `app/tools/rest.py` (NEW)
- `app/tools/browser.py` (NEW)
- `app/tools/database.py` (NEW)
- `app/tools/docker.py` (NEW)
- `app/tools/office.py` (NEW)
- `app/tools/cloud.py` (NEW)
- `app/tools/security.py` (NEW)

---

## Phase 4 — Agent Framework (HIGHEST PRIORITY)

**Goal**: Build the core Agent abstraction that all agents are built upon. This is the foundation for the Agent Factory.

**What exists**: Nothing. Need to build from scratch, reusing patterns from Plugin SDK and Skill system.

### 4.1 Agent Base Class (`app/agents/base.py`)

```python
class Agent(ABC):
    id: str
    name: str
    version: str
    description: str
    status: AgentStatus
    capabilities: list[Capability]
    permissions: list[Permission]
    memory: AgentMemory
    tools: list[ToolDefinition]
    metrics: AgentMetrics
    health: AgentHealth

    @abstractmethod
    async def execute(self, task: Task) -> AgentResult: ...

    # Lifecycle hooks
    async def on_load(self) -> None: ...
    async def on_unload(self) -> None: ...
    async def on_pause(self) -> None: ...
    async def on_resume(self) -> None: ...

    # Communication
    async def send_message(self, target: str, message: Message) -> None: ...
    async def receive_message(self, message: Message) -> None: ...

    # Memory
    async def remember(self, key: str, value: Any) -> None: ...
    async def recall(self, key: str) -> Any: ...
    async def forget(self, key: str) -> None: ...

    # Self-improvement
    async def reflect(self) -> ReflectionReport: ...
    async def learn(self, feedback: Feedback) -> None: ...
```

### 4.2 Agent Lifecycle (`app/agents/lifecycle.py`)
- States: CREATED → LOADED → ACTIVE → PAUSED → STOPPED → UNLOADED
- LifecycleManager: manages state transitions, enforces ordering, publishes events
- Graceful shutdown with timeout
- State persistence across restarts

### 4.3 Agent Registry (enhance from Phase 1) (`app/agents/registry.py`)
- `AgentInstance` — wraps Agent with runtime metadata
- Methods: `register_instance()`, `get_instance()`, `list_instances()`, `unregister_instance()`
- Instance pooling: `acquire()`, `release()` for agent reuse
- Lazy loading: agents loaded on first use

### 4.4 Agent Permissions (`app/agents/permissions.py`)
- Extends Phase 1 security:
- `AgentPermissionSet`: per-agent permission configuration
- Methods: `grant()`, `revoke()`, `check()`, `require()`
- Permission inheritance: agent ← role ← default
- Runtime permission escalation (requires human approval)

### 4.5 Agent Memory (`app/agents/memory.py`)
- `AgentMemory`: per-agent memory sandbox
- Episodic: task outcomes, successes, failures, user feedback
- Semantic: learned facts, patterns, heuristics
- Procedural: optimized workflows, tool usage patterns
- Persisted per-agent in `data/agents/{agent_id}/memory/`
- Uses `MemoryStorage` internally

### 4.6 Agent Communication (`app/agents/communication.py`)
- `AgentMessage` dataclass: sender, recipient(s), type, payload, priority, ttl
- `MessageBus`: pub/sub for agent-to-agent messaging
- `MessageRouter`: delivers to specific agents by ID or capability
- Broadcast, multicast, unicast patterns
- Message validation, rate limiting, persistence for offline delivery

### 4.7 Agent Metrics (`app/agents/metrics.py`)
- `AgentMetrics`: execution_count, success_count, failure_count, avg_latency, p50/p95/p99, cpu_usage, memory_usage, token_usage
- `MetricsCollector`: collects, aggregates, stores metrics
- `MetricsQuery`: query metrics by agent, time range, operation type
- Published to EventBus for monitoring/alerting

### 4.8 Agent Versioning (`app/agents/versioning.py`)
- `AgentVersion`: semver, changelog, diff, compatibility_matrix
- `VersionManager`: create_version(), list_versions(), rollback(), diff()
- Version storage: `data/agents/{agent_id}/versions/`
- Backward compatibility checks on load

### 4.9 Agent Health (`app/agents/health.py`)
- `AgentHealth`: status, last_heartbeat, response_time, error_rate, resource_usage
- `HealthMonitor`: periodic heartbeat check, liveness probe, readiness probe
- `HealthPolicy`: thresholds, escalation rules, auto-recovery actions
- Published health events for dashboard/monitoring

### 4.10 Agent Discovery (`app/agents/discovery.py`)
- `AgentDiscovery`: auto-discover agents from `data/agents/` and `app/agents/builtin/`
- `DiscoveryProtocol`: agents announce capability via EventBus
- `CapabilityIndex`: fast lookup of agents by capability
- `DiscoveryEvent`: agent joined/left/updated events

**Success criteria**:
- [ ] Agent base class works with concrete implementations
- [ ] Full lifecycle works: load → activate → execute → pause → resume → stop → unload
- [ ] Registry can manage 100+ active agents
- [ ] Permissions correctly block unauthorized operations
- [ ] Agent memory persists across restarts
- [ ] Agents can send/receive messages through MessageBus
- [ ] Metrics collected and queryable
- [ ] Versioning supports rollback
- [ ] Health monitor detects and reports failures
- [ ] Discovery finds agents in both builtin and data directories

---

## Phase 5 — Agent Factory (HIGHEST PRIORITY)

**Goal**: Automatically design, generate, validate, and install new agents when gaps are detected.

**What exists**: `SkillGenerator`, `SkillInstaller`, `Sandbox`, `TestRunner`, `EvolutionEngine` patterns.

### 5.1 Capability Analysis (`app/factory/analyzer.py`)
- `CapabilityAnalyzer`: given a goal/task, determines what capabilities are needed
- Uses AI to decompose capability requirements
- Output: `CapabilityRequirements` — list of required capabilities with priorities

### 5.2 Gap Detection (`app/factory/gap.py`)
- `GapDetector`: compares requirements against Agent Registry
- Queries `CapabilityIndex` for existing agents with matching capabilities
- Reports missing capabilities, partially matching agents, and combination opportunities
- `GapReport`: missing, partial, available capabilities; recommended action

### 5.3 Agent Specification Generation (`app/factory/spec.py`)
- `SpecGenerator`: produces detailed agent specification for gaps
- `AgentSpec`: name, version, description, capabilities, dependencies, tools, memory, communication patterns, estimated resource usage
- AI-driven generation using prompts + existing agent patterns
- Validation: spec must be parseable, complete, and consistent

### 5.4 Code Generation (`app/factory/generator.py`)
- `AgentCodeGenerator`: generates production-quality Python code from `AgentSpec`
- Base template: inherits from `Agent`
- Generates: `agent.py`, `__init__.py`, `agent.json` (manifest), `requirements.txt`
- Reuses `PluginManifest` and `SkillGenerator` patterns
- All generated classes have full type hints, docstrings, and logging

### 5.5 Test Generation (`app/factory/test_gen.py`)
- `TestGenerator`: creates `test_{agent_name}.py`
- Unit tests: test each capability independently
- Integration tests: test agent interaction with tools, memory, communication
- Load tests: test agent under concurrent requests
- Uses templates based on existing test patterns

### 5.6 Sandbox Execution (`app/factory/sandbox.py`)
- Reuses `app/evolution/sandbox.py` `Sandbox` class
- Execute generated agent code in isolated environment
- Run generated tests in sandbox
- Collect pass/fail, coverage, resource usage

### 5.7 Benchmarking (`app/factory/benchmark.py`)
- `AgentBenchmark`: measure agent performance against baseline
- Metrics: latency, throughput, accuracy, resource consumption
- `BenchmarkSuite`: predefined test scenarios per capability
- `BenchmarkReport`: comparison against existing agents for same capability

### 5.8 Review (`app/factory/review.py`)
- `CodeReviewer`: AI-powered code review of generated agent
- Checks: correctness, security, style, documentation, test coverage
- `ReviewReport`: issues found, severity, suggested fixes
- Automated fixes for style and docs; manual review for logic issues

### 5.9 Approval (`app/factory/approval.py`)
- Reuses `ApprovalPolicy` from evolution
- `AgentApproval`: human-in-the-loop gating
- Presents: spec, generated code, test results, benchmark comparison, review report
- Approval modes: auto (no human), review (human reviews), approve (human must explicitly approve)

### 5.10 Installation (`app/factory/installer.py`)
- `AgentInstaller`: registers agent in AgentRegistry, copies files to `data/agents/{agent_id}/`
- Creates agent metadata, initializes agent memory
- Links tools, configures permissions
- Creates initial version (v1.0.0)

### 5.11 Registration (`app/factory/registration.py`)
- After installation: register in AgentRegistry, announce via EventBus
- `RegistrationReport`: agent_id, version, capabilities, location
- Updates `CapabilityIndex` for future gap detection

**Success criteria**:
- [ ] Given "I need a web scraper that extracts product prices", Agent Factory produces a working agent
- [ ] Pipeline: analyze → detect gap → generate spec → generate code → generate tests → sandbox → benchmark → review → approve → install → register
- [ ] Human approval blocks installation if review fails
- [ ] Generated agent passes all generated tests
- [ ] Generated agent can be discovered and executed by Agent Manager
- [ ] Factory can create agents with different capability combinations

---

## Phase 6 — Agent Marketplace

**Goal**: Allow agents to be shared, discovered, and installed from remote sources.

### 6.1 Agent Package Format
- `.jarvis-agent` — ZIP package with manifest, code, assets, tests
- Signing: GPG-signed packages for authenticity verification
- Metadata: name, version, author, capabilities, screenshots, docs

### 6.2 Marketplace Protocol
- Registry API: list, search, download, publish, update
- Rating & reviews
- Usage statistics (opt-in)

### 6.3 Offline Marketplace
- Local mirror of marketplace
- Air-gapped installation from files

---

## Phase 7 — Long-term Learning

**Goal**: Agents improve over time based on usage patterns.

### 7.1 Feedback Collection
- `FeedbackCollector`: gather success/failure signals from agent executions
- `Feedback`: rating, comments, execution context, outcome

### 7.2 Pattern Recognition
- `PatternRecognizer`: identify recurring task types, optimal strategies
- `ExecutionGraph`: record task → agent → tools → outcome → time → resources

### 7.3 Continuous Improvement
- Automated agent updates based on learning
- A/B testing of agent variants
- Performance regression detection

---

## Phase 8 — Self-Evolution

**Goal**: JARVIS improves its own codebase.

**What exists**: `EvolutionEngine` — plan, generate, validate, sandbox, test, approve, install, git, version, benchmark

### 8.1 Agent Evolution
- `AgentEvolution`: specialize for agent code evolution
- Same pipeline as Phase 5, but for existing agents
- Fix bugs, add capabilities, optimize performance

### 8.2 Kernel Evolution
- Improve scheduler, registry, security based on runtime data
- Self-healing: detect and fix bottlenecks

---

## Phase 9 — Multi-Model Orchestration

**Goal**: Route tasks to optimal AI models based on cost, speed, quality.

### 9.1 Model Profile
- `ModelProfile`: cost_per_token, latency_p50/p95, capabilities, max_tokens, supported_features

### 9.2 Intelligent Router
- Route tasks by: complexity, required accuracy, budget, latency budget
- Fallback chains: try best model, fall back if unavailable
- Cost optimization: minimize cost while meeting quality requirements

### 9.3 Model Ensemble
- Combine outputs from multiple models
- Majority voting for critical decisions
- Cross-validation of agent-generated code

---

## Phase 10 — Autonomous Project Execution

**Goal**: End-to-end autonomous project execution: goal → plan → build → test → deploy → monitor → learn.

### 10.1 Project Lifecycle Manager
- `Project`: goal, plan, tasks, agents, timeline, budget, metrics
- `ProjectManager`: orchestrates multi-agent project execution
- Milestones, dependencies, critical path tracking

### 10.2 Autonomous Development
- User states a goal (e.g., "Build me a trading bot")
- System: plan → assign agents → generate code → test → deploy → monitor
- Human approval at key checkpoints (design, first deploy, major changes)

### 10.3 Autonomous Operations
- Self-monitoring, self-healing, self-optimization
- Continuous deployment of improvements
- Automated rollback on failures

---

## Implementation Strategy

### Recommended Sprint Order

| Sprint | Phase | Focus |
|--------|-------|-------|
| 1 | P4 | Agent base class, lifecycle, registry |
| 2 | P4 | Agent memory, permissions, metrics |
| 3 | P4 | Agent communication, versioning, health, discovery |
| 4 | P5 | Capability analysis, gap detection, spec generation |
| 5 | P5 | Code generation, test generation |
| 6 | P5 | Sandbox, benchmark, review, approval |
| 7 | P5 | Installation, registration, end-to-end validation |
| 8 | P1 | Scheduler, security enhancement, memory enhancement |
| 9 | P2 | Goal engine (planner, reasoner, reflection, decision) |
| 10 | P3 | Universal tool layer (5 tools) |
| 11 | P3 | Universal tool layer (remaining 5 tools) |
| 12 | P6 | Marketplace |
| 13-14 | P7-P8 | Learning & evolution |
| 15 | P9 | Multi-model orchestration |
| 16 | P10 | Autonomous project execution |

### Key Principles
1. **Production quality only** — no placeholders, strong typing, full test coverage
2. **Build on existing** — reuse Plugin SDK patterns, Sandbox, Evolution Engine
3. **Security first** — every agent has permissions, every tool call is audited
4. **Human approval** — before self-modification, before new agent installation
5. **Reuse over create** — Agent Manager prefers existing agents over Factory
6. **Designed for scale** — thousands of agents, not dozens
