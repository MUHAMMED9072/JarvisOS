from . import entity_types  # noqa: F401 — registers all entity types
from . import relationship_types  # noqa: F401 — registers all relationship types
from .entity import Entity
from .index import EntityIndex, RelationshipIndex
from .relationship import Relationship
from .schema import (
    ENTITY_TYPES,
    EntityType,
    EntityTypeRegistry,
    RELATIONSHIP_TYPES,
    RelationshipType,
    RelationshipTypeRegistry,
)
from .store import GraphStore, KnowledgeGraphEvents
from .traversal import PathResult, shortest_path, all_paths, bfs_traverse, dfs_traverse, k_nearest_neighbors, extract_subgraph
from .pattern_matcher import PatternMatcher, PatternTemplate, MatchResult
from .query import QueryEngine, QueryResult
from .optimizer import QueryOptimizer
from .cascade import CircularDependencyError, would_create_cycle, validate_and_create
from .batch import BatchResult, batch_create_relationships, batch_delete_relationships
from .integrations.agent_registry import AgentRegistry, AgentRecord

__all__ = [
    "ENTITY_TYPES",
    "Entity",
    "EntityIndex",
    "EntityType",
    "EntityTypeRegistry",
    "GraphStore",
    "KnowledgeGraphEvents",
    "RELATIONSHIP_TYPES",
    "Relationship",
    "RelationshipIndex",
    "RelationshipType",
    "RelationshipTypeRegistry",
    "CircularDependencyError",
    "would_create_cycle",
    "validate_and_create",
    "BatchResult",
    "batch_create_relationships",
    "batch_delete_relationships",
    "PathResult",
    "shortest_path",
    "all_paths",
    "bfs_traverse",
    "dfs_traverse",
    "k_nearest_neighbors",
    "extract_subgraph",
    "PatternMatcher",
    "PatternTemplate",
    "MatchResult",
    "QueryEngine",
    "QueryResult",
    "QueryOptimizer",
    "AgentRegistry",
    "AgentRecord",
]
