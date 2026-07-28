# JARVIS OS — Architecture v2

## Design Philosophy

JARVIS is an AI Operating System. Like a traditional OS it provides:
- A **kernel** — scheduling, security, memory, event bus
- **System calls** — the Agent Communication Protocol
- A **process manager** — the Agent Manager
- A **package manager** — the Agent Development System
- **Drivers** — the Universal Tool Layer
- A **file system** — the World Model
- A **shell** — the Supervisor

Humans build the OS once. JARVIS builds almost everything else on top of it.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ USER                                                                 │
│ A human or another system providing a goal                           │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ Goal
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ SUPERVISOR                                                            │
│ The single top-level intelligence.                                   │
│ Interprets goals → gathers context → delegates to Planner.          │
│ NEVER executes work directly.                                        │
│ Only coordinates.                                                     │
│ Memory: Long-term + Working (session context)                        │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ Decomposed goal
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PLANNER                                                              │
│ Decomposes goals into a directed task graph.                        │
│ Estimates resources, identifies dependencies.                       │
│ Consults World Model for context.                                    │
│ Memory: Working (current plan) + Reflection (past plans)            │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ Task graph
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ AGENT MANAGER                                                        │
│ For each task:                                                       │
│   1. Query Capability Registry for existing agents                   │
│   2. If found → assign task                                          │
│   3. If gap → invoke Agent Development System                        │
│   4. Monitor execution, collect results                              │
│ Memory: Working (active assignments) + Metrics (perf history)        │
└──────┬──────────────────────────────────────────────────────┬────────┘
       │ Reuse                                               │ Create
       ▼                                                     ▼
┌──────────────────────┐    ┌──────────────────────────────────────────┐
│ AGENT REGISTRY       │    │ AGENT DEVELOPMENT SYSTEM (ADS)           │
│ Active agents        │    │ Production pipeline:                     │
│ Available agents     │    │                                          │
│ Agent health         │    │ Capability Analyzer                      │
│ Agent versions       │    │ Gap Detector                             │
│ Agent metrics        │    │ Requirements Generator                   │
│                      │    │ Architecture Generator                   │
│ Queried by Agent Mgr │    │ Agent Designer                           │
│ Updated by ADS       │    │ Code Generator                           │
│                      │    │ Test Generator                           │
│                      │    │ Sandbox Execution                        │
│                      │    │ Benchmark                                │
│                      │    │ Security Review                          │
│                      │    │ Performance Review                       │
│                      │    │ Approval (HUMAN)                         │
│                      │    │ Installation                             │
│                      │    │ Registration                             │
│                      │    │ Versioning                               │
│                      │    │ Metrics                                  │
│                      │    │ Learning & Continuous Improvement        │
└──────────────────────┘    └──────────────────────────────────────────┘
       │                                    │
       └──────────────┬─────────────────────┘
                      │ Agent instance
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ EXECUTION LAYER                                                      │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │  Agent A     │  │  Agent B     │  │  Agent C     │  ...          │
│  │  (Planner)   │  │  (Coder)     │  │  (Reviewer)  │               │
│  │              │  │              │  │              │               │
│  │ Memory:      │  │ Memory:      │  │ Memory:      │               │
│  │  Working     │  │  Working     │  │  Working     │               │
│  │  Long-term   │  │  Long-term   │  │  Long-term   │               │
│  │  Reflection  │  │  Reflection  │  │  Reflection  │               │
│  │              │  │              │  │              │               │
│  │ Tools:       │  │ Tools:       │  │ Tools:       │               │
│  │  Planner     │  │  Python      │  │  Git         │               │
│  │  Reasoner    │  │  Git         │  │  Browser     │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                AGENT COMMUNICATION BUS                        │   │
│  │  Request → Delegate → Share → Vote → Report → Escalate       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                          │ Results
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ VERIFICATION & LEARNING                                             │
│  Task result verified                                               │
│  Success/failure recorded                                           │
│  Agent metrics updated                                              │
│  World Model updated                                                │
│  Reflection triggered if patterns detected                          │
│  Results fed back to Supervisor                                     │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ CAPABILITY REGISTRY                                                  │
│ Central index of everything the system can do:                      │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │ Agents   │ │ Tools    │ │ Skills   │ │ Plugins  │               │
│  ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤               │
│  │ Name     │ │ Name     │ │ Name     │ │ Name     │               │
│  │ Version  │ │ Schema   │ │ Intent   │ │ Manifest │               │
│  │ Caps     │ │ Security │ │ Params   │ │ Caps     │               │
│  │ Status   │ │ Provider │ │ Provider │ │ Status   │               │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │ APIs     │ │ Models   │ │ Memory   │ │ Perms    │               │
│  ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤               │
│  │ Endpoint │ │ Provider │ │ Source   │ │ Type     │               │
│  │ Method   │ │ Cost     │ │ Schema   │ │ Scope    │               │
│  │ Schema   │ │ Caps     │ │ Access   │ │ Level    │               │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
│                                                                      │
│ Queried by: Agent Manager, ADS, Planner, Supervisor                 │
│ Updated by: ADS (after installation), Tool Registry, etc.           │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ WORLD MODEL                                                          │
│ The system's internal representation of reality:                    │
│                                                                      │
│  Projects ─── Goals ─── Tasks ─── Agents ─── Results               │
│      │            │         │          │          │                  │
│      ├── People   │         ├── Dependencies   │                     │
│      ├── Files    │         ├── Timeline       │                     │
│      ├── Knowledge│         ├── Resources      │                     │
│      └── Config   │         └── Blockers       │                     │
│                   │                                                 │
│  Agents ─── Capabilities ─── Tools ─── Permissions                  │
│      │            │              │            │                     │
│      ├── Memory   ├── Versions   ├── Security  │                     │
│      ├── Status   ├── Metrics    └── Audit     │                     │
│      └── Health   └── Learned                    │                    │
│                                                                      │
│ Used by: Planner, Reasoner, Decision Engine, Supervisor, ADS        │
│ Updated by: Every agent after execution                              │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ SELF EVOLUTION SYSTEM                                                │
│                                                                      │
│  Observe ──→ Detect Weakness ──→ Generate Improvement               │
│     │               │                    │                           │
│     │               │                    ▼                           │
│     │               │            Sandbox ──→ Tests                   │
│     │               │               │           │                    │
│     │               │               ▼           ▼                    │
│     │               │            Benchmark ──→ Review                │
│     │               │                                    │           │
│     │               │                                    ▼           │
│     │               │                              APPROVAL (HUMAN)  │
│     │               │                                    │           │
│     │               │                                    ▼           │
│     │               │                              Install ──→ Learn │
│     │               │                                                  │
│     └───────────────┴──────────────────────────────────────────────────┘
│                                                                      │
│ Applies to: Agent Framework, ADS, Tools, Kernel, World Model         │
│ Never bypasses human approval                                        │
│ Uses ADS pipeline for implementation                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Agent Lifecycle (Complete)

```
                           ┌──────────┐
                           │  DESIGN   │  ← ADS: Spec + Architecture
                           └────┬─────┘
                                │
                           ┌────▼─────┐
                           │  BUILD    │  ← ADS: Code + Test generation
                           └────┬─────┘
                                │
                           ┌────▼─────┐
                           │ SANDBOX   │  ← ADS: Isolated execution
                           └────┬─────┘
                                │
                           ┌────▼─────┐
                           │  REVIEW   │  ← ADS: Security + Performance
                           └────┬─────┘
                                │
                           ┌────▼─────┐
                           │ APPROVAL  │  ← HUMAN decision
                           └────┬─────┘
                                │ Approved
                           ┌────▼─────┐
                    ┌──────│ INSTALL   │──────┐
                    │      └────┬─────┘      │
                    │           │             │
               ┌────▼────┐ ┌───▼──────┐  ┌───▼──────┐
               │ REGISTER │ │ VERSION  │  │ METRICS  │
               └────┬────┘ │ v1.0.0   │  │ Init     │
                    │      └──────────┘  └──────────┘
                    │
               ┌────▼─────┐
               │ ACTIVATE  │
               └────┬─────┘
                    │
          ┌─────────┼──────────┐
          │         │          │
     ┌────▼───┐ ┌──▼────┐ ┌───▼────┐
     │ RUNNING│ │PAUSED │ │ HEALTH │
     └────┬───┘ └──┬────┘ │ CHECK  │
          │        │      └────────┘
          │        │
          ├────────┘ (resume)
          │
     ┌────▼────┐
     │  RETIRE  │
     └────┬────┘
          │
     ┌────▼────┐    ┌──────────┐
     │ ARCHIVE  │───→│  RECOVER │
     └────┬────┘    └──────────┘
          │
     ┌────▼────┐
     │  DELETE  │
     └─────────┘

Extended operations:
  UPGRADE:   Active → Install(v2) → Activate(v2) → Retire(v1) → Archive(v1)
  DOWNGRADE: Active → Archive(v2) → Recover(v1) → Activate(v1)
  CLONE:     Active → Register(copy) → Activate(copy)
  FORK:      Active → Design(fork) → Build(fork) → ... → Activate(fork)
  MERGE:     Active(a) + Active(b) → Design(merged) → ... → Activate(merged)
```

---

## Agent Type Hierarchy

```
Agent (Abstract Base)
├── SystemAgent (managed by kernel, always running)
│   ├── SupervisorAgent
│   ├── PlannerAgent
│   ├── AgentManagerAgent
│   ├── SchedulerAgent
│   ├── SecurityAgent
│   ├── HealthMonitorAgent
│   └── EvolutionAgent
│
├── ToolAgent (wraps external tools as agents)
│   ├── PythonAgent
│   ├── DockerAgent
│   ├── GitAgent
│   ├── BrowserAgent
│   ├── ShellAgent
│   ├── DatabaseAgent
│   └── ... (unlimited)
│
├── DevelopmentAgent (within ADS pipeline)
│   ├── CapabilityAnalyzerAgent
│   ├── GapDetectorAgent
│   ├── RequirementsAgent
│   ├── ArchitectAgent
│   ├── DesignerAgent
│   ├── CodingAgent
│   ├── TestingAgent
│   ├── ReviewerAgent
│   ├── SecurityReviewerAgent
│   └── BenchmarkAgent
│
├── DomainAgent (user-facing, created by ADS)
│   ├── ResearchAgent
│   ├── TradingAgent
│   ├── MarketingAgent
│   ├── SEOAgent
│   ├── FinanceAgent
│   ├── RiskAgent
│   ├── DocumentationAgent
│   ├── VisionAgent
│   ├── VoiceAgent
│   ├── DeploymentAgent
│   └── ... (unlimited, each with typed capabilities)
│
└── CompositeAgent (orchestrates sub-agents)
    ├── PipelineAgent (sequential sub-agents)
    ├── SwarmAgent (parallel sub-agents with voting)
    ├── ProjectAgent (manages a full project lifecycle)
    └── MetaAgent (manages other agents)
```

---

## Agent Communication Protocol

### Message Types

```python
class MessageType(Enum):
    # Direct communication
    REQUEST      = "request"       # Ask another agent to do work
    RESPONSE     = "response"      # Reply to a request
    DELEGATE     = "delegate"      # Pass a sub-task to another agent
    STATUS       = "status"        # Report current status
    
    # Coordination
    ESCALATE     = "escalate"      # Raise issue to higher authority
    VOTE_REQUEST = "vote_request"  # Ask agents to vote on a decision
    VOTE         = "vote"          # Cast a vote
    NEGOTIATE    = "negotiate"     # Propose a trade-off
    CONSENSUS    = "consensus"     # Report group consensus
    
    # Knowledge sharing
    SHARE_MEMORY  = "share_memory" # Share a memory with another agent
    SHARE_PLAN    = "share_plan"   # Share execution plan
    SHARE_RESULT  = "share_result" # Share execution result
    BROADCAST     = "broadcast"    # Send to all interested agents
    
    # System
    HEARTBEAT     = "heartbeat"    # Liveness check
    HEALTH        = "health"       # Health report
    ERROR         = "error"        # Error report
    METRICS       = "metrics"      # Performance metrics
```

### Message Envelope

```python
@dataclass
class AgentMessage:
    id: str                          # UUID
    type: MessageType                # Message semantics
    sender: str                      # Agent ID
    recipient: str | list[str]       # Agent ID(s) or "*" for broadcast
    correlation_id: str | None       # Links related messages (request↔response)
    payload: Any                     # The actual content
    priority: int = 0                # 0=normal, 1=high, 2=critical
    ttl: float = 30.0                # Seconds before message expires
    timestamp: float = 0.0           # Creation time
    signature: str | None = None     # Cryptographic signature (future)
```

### Communication Patterns

| Pattern | Description |
|---------|-------------|
| Request-Response | Agent A sends REQUEST to Agent B, B replies with RESPONSE |
| Publish-Subscribe | Agents subscribe to message types on the bus |
| Delegate-Return | Agent A delegates to B, B reports back when done |
| Broadcast | One agent broadcasts to all matching subscribers |
| Voting | One agent requests votes, agents cast VOTE, requester computes |
| Escalate | Agent escalates to Supervisor when it cannot resolve |
| Negotiate | Two agents negotiate to resolve conflicts |
| Pipeline | Output of one agent feeds into next (via shared memory) |

---

## Capability Registry — Design

### Core Model

```python
@dataclass
class Capability:
    id: str                          # Unique identifier
    name: str                        # Human-readable name
    description: str                 # What this capability does
    category: CapabilityCategory     # Agent, Tool, Skill, Plugin, API, Model, Memory, Permission
    provider_id: str                 # Which agent/tool/skill provides this
    provider_type: ProviderType      # AGENT, TOOL, SKILL, PLUGIN, API, MODEL
    version: str                     # Semantic version
    input_schema: dict | None        # JSON Schema for inputs
    output_schema: dict | None       # JSON Schema for outputs
    dependencies: list[str]          # Capability IDs this depends on
    metadata: dict                   # Extensible metadata
    status: CapabilityStatus         # ACTIVE, DEPRECATED, RETIRED
    quality_score: float             # 0.0 to 1.0 (based on metrics)
```

### Registry Indexes

```python
class CapabilityRegistry:
    # Primary indexes
    by_id: dict[str, Capability]
    by_name: dict[str, list[Capability]]
    by_category: dict[CapabilityCategory, list[Capability]]
    by_provider: dict[str, list[Capability]]  # provider_id → capabilities
    
    # Specialized indexes
    by_agent: dict[str, list[Capability]]      # Agent ID → capabilities
    by_tool_name: dict[str, Capability]         # Tool name → capability
    by_skill_intent: dict[str, Capability]      # Skill intent → capability
    by_plugin: dict[str, list[Capability]]      # Plugin ID → capabilities
    by_api_endpoint: dict[str, Capability]       # API route → capability
    by_model_capability: dict[str, list[Capability]]  # Model capability → capabilities
    by_permission: dict[Permission, list[Capability]] # Permission → capabilities
    
    # Search
    def search(query: str, filters: dict) -> list[Capability]: ...
    def find_providers(required: list[str]) -> dict[str, list[Capability]]: ...
    def find_gaps(required: list[str]) -> GapReport: ...
    def get_similar(capability_id: str) -> list[Capability]: ...
```

### Queries the Registry Must Answer Instantly

| Question | Query |
|----------|-------|
| Can the system write Python code? | `by_name["python_execution"]` |
| Which agents can browse the web? | `by_category["AGENT"]` filtered by `browser` |
| Is there a skill for intent "calculator"? | `by_skill_intent["calculator"]` |
| What tools are available? | `by_category["TOOL"]` |
| What AI models are available? | `by_category["MODEL"]` |
| Which APIs exist? | `by_category["API"]` |
| What permissions are defined? | `by_category["PERMISSION"]` |
| Are there agents that can trade stocks? | `search("stock trading")` |
| What are all capabilities of agent X? | `by_agent["agent_x"]` |
| What capabilities are missing? | `find_gaps(["web_scraping", "data_analysis"])` |

---

## World Model — Design

### Entity Types

```python
@dataclass
class WorldEntity:
    id: str
    type: EntityType         # PROJECT, GOAL, PERSON, COMPANY, TASK, KNOWLEDGE,
                             # FILE, AGENT, CAPABILITY, TOOL, RESOURCE, etc.
    name: str
    properties: dict         # Type-specific properties
    relationships: list[Relationship]
    memory_refs: list[str]   # References to entries in memory
    created_at: float
    updated_at: float
    version: int

@dataclass
class Relationship:
    source_id: str           # Entity ID
    target_id: str           # Entity ID
    type: RelationType       # DEPENDS_ON, CONTAINS, ASSIGNED_TO, CREATED_BY,
                             # RELATED_TO, BLOCKS, TRIGGERS, IMPLEMENTS
    weight: float            # 0.0 to 1.0 (strength of relationship)
    metadata: dict
```

### Example World Model Graph

```
Project: "Build Trading Bot"
  ├── Goal: "Fetch market data"
  │   └── Task: "Implement data fetcher"
  │       ├── Agent: "CodingAgent_1" (ASSIGNED_TO)
  │       ├── File: "data_fetcher.py" (CREATED_BY)
  │       ├── Capability: "python_execution" (DEPENDS_ON)
  │       └── Dependency: "MarketDataAPI" (DEPENDS_ON)
  ├── Goal: "Analyze patterns"
  │   └── Task: "Implement strategy analyzer"
  │       ├── Agent: "CodingAgent_1" (ASSIGNED_TO)
  │       ├── Agent: "ResearchAgent_2" (CONSULTS)
  │       └── Knowledge: "trading_strategies" (RELATED_TO)
  ├── Person: "User" (OWNER)
  ├── Knowledge: "financial_markets" (RELATED_TO)
  └── Resource: "compute_credits" (CONSUMES)
```

### World Model Operations

| Operation | Description |
|-----------|-------------|
| `add_entity()` | Create a new entity |
| `update_entity()` | Modify an entity's properties |
| `add_relationship()` | Link two entities |
| `remove_relationship()` | Unlink two entities |
| `get_entity()` | Get entity by ID |
| `query()` | Find entities matching criteria |
| `traverse()` | Walk the graph from a starting entity |
| `shortest_path()` | Find connection between two entities |
| `subgraph()` | Extract a subgraph around an entity |
| `diff()` | Compare two versions of the model |

Updated by: Every agent after completing a task
Queried by: Planner (for context), Reasoner (for evidence), Supervisor (for state)

---

## Revised Roadmap

### Dependency Graph (simplified)

```
P1 ──→ P2 ──→ P3 ──→ P4 ──→ P5 ──→ P6 ──→ P7 ──→ P8 ──→ P9 ──→ P10
│      │      │      │      │      │      │      │      │      │
│      │      │      │      │      │      │      │      │      │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴── Timeline
```

P1 → P2 → P3 → P4 → P5 must be built by humans.
After P5 (ADS), JARVIS can build most of P6+ autonomously.

---

### Phase 1 — AI OS Kernel

**Theme**: The absolute foundation. Everything depends on this.

**Existing assets**: EventBus, ServiceRegistry, Config, AI providers, Memory base

| Component | Description | Build on |
|-----------|-------------|----------|
| 1.1 EventBus | Already complete | Existing |
| 1.2 ServiceRegistry | Already complete | Existing |
| 1.3 Config System | Already complete | Existing |
| 1.4 Scheduler | Task scheduling, cron, interval, priority queue | New |
| 1.5 Security Layer | Kernel-level permissions (elevate from Plugin SDK) | Plugin SDK security.py |
| 1.6 Base Memory | Enhance with vector storage, semantic search | memory/knowledge.py, search.py stubs |
| 1.7 World Model Foundation | Entity schema, storage, basic CRUD | New |
| 1.8 Logging & Audit | Structured logging, audit trail for all operations | Existing logger |

**Success criteria**:
- [ ] Scheduler runs 1000+ tasks with cron/interval/once triggers
- [ ] Security layer enforces permissions at kernel level
- [ ] Vector memory stores/retrieves 10K+ embeddings, KNN < 100ms
- [ ] World Model supports entity CRUD + relationship queries
- [ ] All components publish lifecycle events

**Human builds**: 100% of this phase

---

### Phase 2 — Core Intelligence

**Theme**: The thinking layer. Without this, nothing above can work intelligently.

**Existing assets**: AIConfig, AIRouter, AIManager, AIProvider base, PromptTemplate, ToolRegistry (partial)

| Component | Description | Build on |
|-----------|-------------|----------|
| 2.1 Supervisor | Top-level coordinator, goal interpretation, context assembly | New |
| 2.2 Planner | Goal decomposition → task graph, resource estimation | Evolution planner + New |
| 2.3 Reasoner | Alternative evaluation, strategy comparison, justification | AIManager.reason() + New |
| 2.4 Reflection Engine | Post-execution analysis, pattern recognition, heuristic update | New |
| 2.5 Decision Engine | Weighted scoring, multi-criteria decisions | New |
| 2.6 World Model (complete) | Full graph operations, query, traversal, subgraph extraction | P1.7 foundation |

**Success criteria**:
- [ ] Supervisor correctly interprets and delegates 10+ diverse goals
- [ ] Planner decomposes "build a trading bot" into 10-20 actionable tasks
- [ ] Reasoner produces coherent, verifiable justifications
- [ ] Reflection correctly identifies root causes of failures
- [ ] Decision engine selects optimal approach >80% of the time
- [ ] World Model accurately tracks project state across agent executions

**Human builds**: 100% of this phase

---

### Phase 3 — Agent Framework

**Theme**: The agent abstraction itself. Every agent in the system implements this.

**Existing assets**: Plugin base class patterns, Skill base class patterns

| Component | Description |
|-----------|-------------|
| 3.1 Agent Base Class | ABC with execute(), lifecycle hooks, type system |
| 3.2 Agent Lifecycle Manager | State machine: DESIGN→BUILD→SANDBOX→REVIEW→APPROVE→INSTALL→REGISTER→ACTIVATE→RUNNING→PAUSE→RESUME→RETIRE→ARCHIVE→DELETE |
| 3.3 Agent Registry | Register, unregister, list, search, get by ID/capability |
| 3.4 Agent Memory | Per-agent: Working, Long-term, Reflection, Shared, Project, Knowledge |
| 3.5 Agent Communication | MessageBus, MessageRouter, protocol implementation |
| 3.6 Agent Metrics | Execution count, success rate, latency p50/p95/p99, resource usage |
| 3.7 Agent Health | Heartbeat, liveness probe, readiness probe, auto-recovery |
| 3.8 Agent Versioning | SemVer, changelog, diff, rollback, version history |

**Success criteria**:
- [ ] 3 concrete agent types implement the base class (System, Tool, Domain)
- [ ] Lifecycle: full state machine works with all transitions
- [ ] Registry manages 100+ agents with sub-millisecond lookup
- [ ] Agent memory persists across restarts, supports all 6 memory types
- [ ] Two agents can communicate via MessageBus
- [ ] Metrics are collected and queryable per-agent
- [ ] Health monitor detects failures within 5 seconds
- [ ] Version rollback completes in <1 second

**Human builds**: 100% of this phase

---

### Phase 4 — Capability Registry

**Theme**: The system's self-knowledge. Without this, JARVIS cannot know what it already has.

| Component | Description |
|-----------|-------------|
| 4.1 Capability Index | Central registry of all capabilities (agents, tools, skills, plugins, APIs, models) |
| 4.2 Agent Capability Mapper | Maps existing agents to their capabilities |
| 4.3 Tool Capability Mapper | Maps tools to capabilities (wraps ToolRegistry) |
| 4.4 Skill Capability Mapper | Maps skills to capabilities (integrates SkillManager) |
| 4.5 Plugin Capability Mapper | Maps plugins to capabilities (integrates PluginManager) |
| 4.6 API Capability Mapper | Maps REST API endpoints to capabilities |
| 4.7 Model Capability Mapper | Maps AI models to capabilities (integrates routing) |
| 4.8 Cross-Reference Engine | Answers: "what can do X?", "who depends on Y?", "how to achieve Z?" |

**Success criteria**:
- [ ] Registry indexes all existing agents, tools, skills, plugins, APIs, models
- [ ] Cross-reference engine answers queries in <50ms
- [ ] `find_gaps()` correctly identifies missing capabilities
- [ ] `find_providers()` returns all capable agents sorted by quality score
- [ ] No duplicate agent can be registered for same capability

**Human builds**: 100% of this phase

---

### Phase 5 — Agent Development System (ADS)

**Theme**: The system's ability to create new agents autonomously. The crown jewel.

**Existing assets**: SkillGenerator, Plugin scaffolding, Sandbox, TestRunner, ApprovalPolicy, Evolution Engine

| Component | Description | Build on |
|-----------|-------------|----------|
| 5.1 Capability Analyzer | Given requirements, determines what capabilities are needed | New |
| 5.2 Gap Detector | Queries Capability Registry, reports missing/partial/available | P4 Gap Finder |
| 5.3 Requirements Generator | Produces detailed AgentSpec from gaps | New |
| 5.4 Architecture Generator | Designs agent architecture (components, communication, memory) | New |
| 5.5 Agent Designer | Specifies agent internals (state, behavior, tools, APIs) | New |
| 5.6 Code Generator | Generates production Python code | SkillGenerator + Plugin scaffolding |
| 5.7 Test Generator | Generates unit + integration tests | New |
| 5.8 Sandbox Executor | Runs agent in isolated environment | Sandbox |
| 5.9 Benchmark Runner | Measures agent performance | Benchmark (partial) |
| 5.10 Security Reviewer | Static analysis, permission validation | New |
| 5.11 Performance Reviewer | Resource usage analysis | New |
| 5.12 Approval Gate | Human-in-the-loop gating | ApprovalPolicy |
| 5.13 Installer | Filesystem installation, dependency resolution | SkillInstaller + Plugin installer |
| 5.14 Registrar | Register in Agent Registry + Capability Registry | P3.3 + P4 |
| 5.15 Versioner | Create initial version, semver assignment | P3.8 |
| 5.16 Metrics Collector | Baseline metrics collection | P3.6 |
| 5.17 Learning Loop | Post-installation feedback collection | New |
| 5.18 Continuous Improver | Automated improvements based on metrics | Evolution Engine |

**Success criteria**:
- [ ] End-to-end pipeline: "I need a web scraper" → working, tested agent
- [ ] All pipeline stages complete without human intervention (except approval)
- [ ] Generated agent passes 100% of auto-generated tests
- [ ] Generated agent is security-reviewed (no dangerous imports/patterns)
- [ ] Generated agent is discoverable via Capability Registry
- [ ] Generated agent has correct version, metrics, health monitoring
- [ ] Pipeline completes in <5 minutes for a simple agent
- [ ] Human approval correctly blocks agents with security issues

**Human builds**: 100% of this phase

---

### Phase 6 — Universal Tool Layer

**Theme**: Everything external as a tool. After this phase, agents can interact with the world.

| Tool | Description |
|------|-------------|
| 6.1 PythonTool | Execute Python code (sandboxed) |
| 6.2 ShellTool | Execute shell commands (sandboxed) |
| 6.3 GitTool | Git operations (clone, commit, push, branch, merge) |
| 6.4 FileTool | File read/write/copy/move/delete with path safety |
| 6.5 RESTTool | HTTP requests (GET, POST, PUT, DELETE, PATCH) |
| 6.6 BrowserTool | Web scraping, search, form filling |
| 6.7 DatabaseTool | SQL query execution (SQLite first, extensible) |
| 6.8 DockerTool | Docker container management |
| 6.9 OfficeTool | Document generation (PDF, MD, HTML, CSV) |
| 6.10 CloudTool | Cloud API adapters (extensible) |
| 6.11 SSHTool | Remote command execution |
| 6.12 EmailTool | Send/receive emails |
| 6.13 MessagingTool | Slack, Discord, Telegram bots |

**Built by**: ADS + Human (first tool built by human, rest can be built by ADS)
**Success criteria**: 13 tools, each with unit tests, security validation, audit logging

---

### Phase 7 — Agent Ecosystem

**Theme**: Full lifecycle management at scale.

| Component | Description |
|-----------|-------------|
| 7.1 Agent Discovery | Auto-discover agents from filesystem |
| 7.2 Agent Marketplace | Package, share, install remote agents |
| 7.3 Agent Retirement | Graceful shutdown, dependency check |
| 7.4 Agent Archival | Compress and store retired agents |
| 7.5 Agent Recovery | Restore from archive |
| 7.6 Agent Cloning | Create copies for experimentation |
| 7.7 Agent Forking | Branch agent development |
| 7.8 Agent Merging | Combine two agents |

**Built by**: ADS (after P5, ADS can build these)
**Success criteria**: Full lifecycle operations work at scale (1000+ agents)

---

### Phase 8 — Long-term Learning & Knowledge

**Theme**: Agents improve over time.

| Component | Description |
|-----------|-------------|
| 8.1 Cross-Agent Pattern Recognition | Learn from all agents' successes/failures |
| 8.2 Strategy Optimization | Improve Planner and Reasoner heuristics |
| 8.3 Knowledge Distillation | Extract general knowledge from specific agent experiences |
| 8.4 Capability Quality Scoring | Update Capability Registry quality scores over time |

**Built by**: ADS
**Success criteria**: System measurably improves over time (fewer failures, faster execution)

---

### Phase 9 — Self-Evolution

**Theme**: JARVIS improves its own source code.

**Existing assets**: Full Evolution Engine (plan, generate, sandbox, test, approve, install, git, version, benchmark)

| Component | Description |
|-----------|-------------|
| 9.1 System Evolution | Improve kernel, scheduler, security, memory |
| 9.2 Agent Framework Evolution | Improve Agent base, lifecycle, communication |
| 9.3 ADS Evolution | Improve the agent development pipeline itself |
| 9.4 Tool Evolution | Improve existing tools, add new ones |
| 9.5 Meta-Evolution | Improve the evolution process itself |

**Built by**: ADS (Self-Evolution is the ultimate expression of ADS)
**Success criteria**: JARVIS can improve any part of itself (with human approval)

---

### Phase 10 — Full Autonomy

**Theme**: End-to-end autonomous operation.

| Component | Description |
|-----------|-------------|
| 10.1 Autonomous Project Execution | Goal → plan → execute → verify → learn (full cycle) |
| 10.2 Multi-Agent Orchestration | Complex workflows with dozens of collaborating agents |
| 10.3 Human Oversight Layer | Dashboard for monitoring, intervention, policy setting |
| 10.4 Self-Healing | Detect and fix problems without human involvement |
| 10.5 Continuous Deployment | Automated rollout of improvements |

**Built by**: ADS (final phase — system that builds itself)
**Success criteria**: JARVIS can take a high-level goal and deliver a production-quality outcome with minimal human oversight

---

## Key Design Decisions Summary

| Decision | Rationale |
|----------|-----------|
| Supervisor never executes | Prevents coupling, maintains clear delegation, enables audit |
| Single Capability Registry | Single source of truth, prevents duplicate agents, enables gap analysis |
| ADS is a pipeline of specialized agents | Each agent in ADS does one thing well, composable, testable |
| Agent types are hierarchical | Enables code reuse, polymorphism, capability inheritance |
| Communication is message-based | Decoupled, asynchronous, traceable, replayable |
| World Model is a graph | Relationships matter as much as entities, enables path finding |
| Self-evolution requires human approval | Safety constraint — never bypasses |
| Everything external is a Tool | Uniform interface, security boundary, audit trail |
| P1-P5 human-built, P6+ ADS-built | Humans build the factory, factory builds everything else |

---

## Component Inventory (Summary)

| Component | Status | Phase |
|-----------|--------|-------|
| EventBus | EXISTS | P1 |
| ServiceRegistry | EXISTS | P1 |
| Config | EXISTS | P1 |
| Logger | EXISTS | P1 |
| AI Providers | EXISTS | P2 |
| AI Router | EXISTS | P2 |
| Prompt Templates | EXISTS | P2 |
| Tool Registry | EXISTS (partial) | P6 |
| Skill Manager | EXISTS | P4 |
| Plugin Manager | EXISTS | P4 |
| Skill Generator | EXISTS (simple) | P5 |
| Plugin Scaffolding | EXISTS | P5 |
| Sandbox | EXISTS | P5 |
| Test Runner | EXISTS | P5 |
| Approval Policy | EXISTS | P5 |
| Evolution Engine | EXISTS | P9 |
| Memory (base) | EXISTS | P1 |
| Memory (knowledge/search) | STUB | P1 |
| Memory (preferences/context/projects) | STUB | P3 |
| Scheduler | NEW | P1 |
| Security (kernel level) | NEW | P1 |
| World Model | NEW | P1+P2 |
| Supervisor | NEW | P2 |
| Planner (general) | NEW | P2 |
| Reasoner (general) | NEW | P2 |
| Reflection Engine | NEW | P2 |
| Decision Engine | NEW | P2 |
| Agent Base Class | NEW | P3 |
| Agent Lifecycle Manager | NEW | P3 |
| Agent Registry | NEW | P3 |
| Agent Memory (per-agent) | NEW | P3 |
| Agent Communication | NEW | P3 |
| Agent Metrics | NEW | P3 |
| Agent Health | NEW | P3 |
| Agent Versioning | NEW | P3 |
| Capability Registry | NEW | P4 |
| ADS (full pipeline, 18 stages) | NEW | P5 |
| Universal Tools (13 tools) | NEW (most) | P6 |
| Agent Marketplace | NEW | P7 |
| Long-term Learning | NEW | P8 |
| Self-Evolution (applied) | NEW | P9 |
| Full Autonomy | NEW | P10 |
