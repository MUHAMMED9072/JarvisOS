from __future__ import annotations

from typing import Any


class QueryOptimizer:
    """Selects optimal traversal strategy based on query characteristics.

    Provides cost estimates and strategy recommendations without
    actually executing queries.
    """

    STRATEGY_BFS = "bfs"
    STRATEGY_DFS = "dfs"
    STRATEGY_SHORTEST_PATH = "shortest_path"
    STRATEGY_PATTERN_MATCH = "pattern_match"
    STRATEGY_SUBGRAPH = "subgraph"

    def recommend_strategy(
        self,
        query_type: str,
        estimated_depth: int = 5,
        estimated_fan_out: int = 3,
    ) -> str:
        """Recommend optimal traversal strategy.

        Args:
            query_type: Type hint ('traverse', 'path', 'pattern', 'subgraph').
            estimated_depth: Expected traversal depth.
            estimated_fan_out: Expected average edges per node.
        """
        if query_type == "path":
            if estimated_depth > 15:
                return self.STRATEGY_BFS
            return self.STRATEGY_SHORTEST_PATH

        if query_type == "pattern":
            return self.STRATEGY_PATTERN_MATCH

        if query_type == "subgraph":
            return self.STRATEGY_SUBGRAPH

        # For general traversal, BFS is better for shallow/wide graphs,
        # DFS for deep/narrow graphs.
        if estimated_fan_out * estimated_depth > 100:
            return self.STRATEGY_BFS
        return self.STRATEGY_DFS

    def estimate_cost(
        self,
        strategy: str,
        node_count: int = 1000,
        edge_count: int = 5000,
        depth: int = 5,
        fan_out: int = 3,
    ) -> dict[str, Any]:
        """Estimate execution cost for a given strategy."""
        base: dict[str, Any] = {
            "strategy": strategy,
            "estimated_nodes_visited": 0,
            "estimated_edges_traversed": 0,
            "complexity": "O(1)",
        }

        if strategy == self.STRATEGY_BFS:
            visited = min(node_count, fan_out ** depth)
            base["estimated_nodes_visited"] = visited
            base["estimated_edges_traversed"] = visited * fan_out
            base["complexity"] = f"O(V+E) ~ O({node_count}+{edge_count})"
        elif strategy == self.STRATEGY_DFS:
            visited = min(node_count, fan_out ** depth)
            base["estimated_nodes_visited"] = visited
            base["estimated_edges_traversed"] = visited * fan_out
            base["complexity"] = f"O(V+E) ~ O({node_count}+{edge_count})"
        elif strategy == self.STRATEGY_SHORTEST_PATH:
            base["estimated_nodes_visited"] = fan_out ** depth
            base["estimated_edges_traversed"] = (fan_out ** depth) * fan_out
            base["complexity"] = "O(V+E)"
        elif strategy == self.STRATEGY_PATTERN_MATCH:
            base["estimated_nodes_visited"] = edge_count
            base["estimated_edges_traversed"] = edge_count
            base["complexity"] = "O(E)"
        elif strategy == self.STRATEGY_SUBGRAPH:
            visited = min(node_count, fan_out ** depth)
            base["estimated_nodes_visited"] = visited
            base["estimated_edges_traversed"] = visited * fan_out
            base["complexity"] = f"O(V+E) ~ O({visited}+{visited * fan_out})"

        return base

    def should_cache(self, query_type: str, frequency: int = 1) -> bool:
        """Recommend whether results should be cached."""
        return frequency >= 2 or query_type in ("subgraph", "pattern")
