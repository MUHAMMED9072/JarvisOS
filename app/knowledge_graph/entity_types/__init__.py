from __future__ import annotations

from app.knowledge_graph.schema import ENTITY_TYPES, EntityType

# Register all 30+ entity types.  Only registers types not already
# registered by schema.py so existing field-level validation is preserved.


def _register_if_new(name: str, desc: str) -> None:
    if not ENTITY_TYPES.is_valid(name):
        ENTITY_TYPES.register(EntityType(name, description=desc))


# --- Project Management ---
_register_if_new("project", "A project or initiative")
_register_if_new("goal", "A goal or objective")
_register_if_new("task", "A task or action item")
_register_if_new("milestone", "A project milestone")
_register_if_new("changelog", "A changelog entry")
_register_if_new("version", "A software version")

# --- Code & Artifacts ---
_register_if_new("file", "A file or source module")
_register_if_new("code_module", "A code module or package")
_register_if_new("artifact", "A build artifact or deliverable")

# --- Agents ---
_register_if_new("agent", "An AI agent")

# --- Capabilities & Tools ---
_register_if_new("capability", "A capability or function")
_register_if_new("tool", "A tool or utility")
_register_if_new("skill", "A skill or expertise")
_register_if_new("plugin", "A plugin or extension")
_register_if_new("api_endpoint", "An API endpoint")
_register_if_new("model", "An AI model")

# --- Users & Access ---
_register_if_new("user", "A system user")
_register_if_new("permission", "A permission definition")
_register_if_new("role", "A role definition")

# --- Knowledge & Data ---
_register_if_new("knowledge", "A knowledge entry")
_register_if_new("memory_entry", "A memory entry")
_register_if_new("pattern", "A recognized pattern")
_register_if_new("heuristic", "A heuristic rule")

# --- Workflows & Pipelines ---
_register_if_new("workflow", "A workflow definition")
_register_if_new("pipeline", "A processing pipeline")

# --- Events & Monitoring ---
_register_if_new("event", "A system event")
_register_if_new("metric", "A performance metric")
_register_if_new("agent_metrics", "Agent-specific metrics data")
_register_if_new("audit_log", "An audit log entry")
_register_if_new("incident", "A system incident")

# --- Policy ---
_register_if_new("policy", "A governance policy")

# --- Evolution ---
_register_if_new("evolution_attempt", "A self-evolution attempt with outcome")
_register_if_new("evolution_scan", "A scan result identifying improvement opportunities")
_register_if_new("evolution_patch", "A generated patch for self-evolution")
_register_if_new("evolution_strategy", "A meta-evolution strategy")

# --- General ---
_register_if_new("concept", "A generic concept or idea")
