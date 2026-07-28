from __future__ import annotations

from app.knowledge_graph.schema import RELATIONSHIP_TYPES, RelationshipType


def _register_if_new(name: str, desc: str) -> None:
    if not RELATIONSHIP_TYPES.is_valid(name):
        RELATIONSHIP_TYPES.register(RelationshipType(name, description=desc))


# --- Dependency ---
_register_if_new("depends_on", "A depends on B")
_register_if_new("dependency_of", "A is a dependency of B")

# --- Containment ---
_register_if_new("contains", "A contains B")
_register_if_new("part_of", "A is part of B")

# --- Usage ---
_register_if_new("uses", "A uses B")
_register_if_new("used_by", "A is used by B")

# --- Creation ---
_register_if_new("created_by", "A was created by B")
_register_if_new("created", "A created B")

# --- References ---
_register_if_new("references", "A references B")
_register_if_new("referenced_by", "A is referenced by B")

# --- Implementation ---
_register_if_new("implements", "A implements B")
_register_if_new("implemented_by", "A is implemented by B")

# --- Extension ---
_register_if_new("extends", "A extends B")
_register_if_new("extended_by", "A is extended by B")

# --- Composition ---
_register_if_new("composes", "A composes B")
_register_if_new("composed_of", "A is composed of B")

# --- Ownership ---
_register_if_new("owns", "A owns B")
_register_if_new("owned_by", "A is owned by B")

# --- Management ---
_register_if_new("manages", "A manages B")
_register_if_new("managed_by", "A is managed by B")
_register_if_new("assigns", "A assigns B")
_register_if_new("assigned_to", "A is assigned to B")

# --- Communication ---
_register_if_new("communicates_with", "A communicates with B")
_register_if_new("triggers", "A triggers B")
_register_if_new("triggered_by", "A is triggered by B")
_register_if_new("notifies", "A notifies B")

# --- Data Flow ---
_register_if_new("produces", "A produces B")
_register_if_new("consumes", "A consumes B")
_register_if_new("transforms", "A transforms B")
_register_if_new("transformed_by", "A is transformed by B")
_register_if_new("maps_to", "A maps to B")

# --- Authorization ---
_register_if_new("grants", "A grants B")
_register_if_new("grants_access_to", "A grants access to B")
_register_if_new("restricts", "A restricts B")

# --- Categorization ---
_register_if_new("categorizes", "A categorizes B")
_register_if_new("classified_as", "A is classified as B")
_register_if_new("tags", "A tags B")

# --- History ---
_register_if_new("supersedes", "A supersedes B")
_register_if_new("superseded_by", "A is superseded by B")
_register_if_new("precedes", "A precedes B")
_register_if_new("follows", "A follows B")
_register_if_new("derived_from", "A is derived from B")

# --- Baseline ---
_register_if_new("related_to", "A is related to B")
