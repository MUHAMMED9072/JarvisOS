from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class PatternTemplate:
    """A template describing a subgraph pattern to match.

    - node_types: dict of label -> expected entity type ("" = any)
    - edges: list of (source_label, rel_type, target_label)
    """
    node_types: dict[str, str] = field(default_factory=dict)
    edges: list[tuple[str, str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_types": dict(self.node_types),
            "edges": [(s, r, t) for s, r, t in self.edges],
        }


@dataclass
class MatchResult:
    """A single match of a pattern in the graph."""
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {label: dict(data) for label, data in self.nodes.items()},
            "edges": [dict(e) for e in self.edges],
        }


class PatternMatcher:
    """Match declarative subgraph patterns against the Knowledge Graph."""

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def match(self, pattern: PatternTemplate, max_results: int = 50) -> list[MatchResult]:
        """Find all subgraphs matching the given pattern template."""
        results: list[MatchResult] = []
        if not pattern.edges:
            return results

        first_source, first_rel_type, first_target = pattern.edges[0]

        # Seed candidates from the first edge
        candidates = self._find_edge_candidates(first_source, first_rel_type, first_target)

        for cand_source, cand_rel, cand_target in candidates:
            if len(results) >= max_results:
                break
            mapping: dict[str, dict[str, Any]] = {}
            matched_edges: list[dict[str, Any]] = [cand_rel]

            source_ent = self._store.get_entity(cand_source)
            target_ent = self._store.get_entity(cand_target)

            if not self._type_match(first_source, source_ent, pattern):
                continue
            if not self._type_match(first_target, target_ent, pattern):
                continue

            mapping[first_source] = source_ent.to_dict() if source_ent else {}
            mapping[first_target] = target_ent.to_dict() if target_ent else {}

            # Try to extend with remaining edges
            ok = True
            for src_label, rel_type, tgt_label in pattern.edges[1:]:
                found = False
                for nlabel, ndata in mapping.items():
                    eid = ndata.get("id", "")
                    for rel in self._store.get_outgoing_relationships(eid):
                        if rel["type"] != rel_type:
                            continue
                        nxt = rel["target_id"]
                        nxt_ent = self._store.get_entity(nxt)
                        if not nxt_ent:
                            continue
                        expected_label = tgt_label if nlabel == src_label else src_label
                        if expected_label in mapping:
                            if mapping[expected_label].get("id") != nxt:
                                continue
                        elif not self._type_match(expected_label, nxt_ent, pattern):
                            continue
                        if expected_label not in mapping:
                            mapping[expected_label] = nxt_ent.to_dict()
                        matched_edges.append(rel)
                        found = True
                        break
                    if found:
                        break
                if not found:
                    # Try backward
                    for nlabel, ndata in mapping.items():
                        eid = ndata.get("id", "")
                        for rel in self._store.get_incoming_relationships(eid):
                            if rel["type"] != rel_type:
                                continue
                            src = rel["source_id"]
                            src_ent = self._store.get_entity(src)
                            if not src_ent:
                                continue
                            expected_label = tgt_label if nlabel == src_label else src_label
                            if expected_label in mapping:
                                if mapping[expected_label].get("id") != src:
                                    continue
                            elif not self._type_match(expected_label, src_ent, pattern):
                                continue
                            if expected_label not in mapping:
                                mapping[expected_label] = src_ent.to_dict()
                            matched_edges.append(rel)
                            found = True
                            break
                        if found:
                            break

                if not found:
                    ok = False
                    break

            if ok and all(label in mapping for label in pattern.node_types):
                results.append(MatchResult(nodes=dict(mapping), edges=list(matched_edges)))

        return results

    def _find_edge_candidates(
        self,
        source_label: str,
        rel_type: str,
        target_label: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        candidates: list[tuple[str, dict[str, Any], str]] = []
        seen: set[str] = set()
        for rel in self._store.get_relationships_by_type(rel_type):
            key = f"{rel['source_id']}:{rel['id']}:{rel['target_id']}"
            if key not in seen:
                seen.add(key)
                candidates.append((rel["source_id"], rel, rel["target_id"]))
        return candidates

    def _type_match(self, label: str, entity: Any | None, pattern: PatternTemplate) -> bool:
        if entity is None:
            return False
        expected_type = pattern.node_types.get(label, "")
        if not expected_type:
            return True
        return entity.type == expected_type
