from __future__ import annotations

from app.knowledge_graph.optimizer import QueryOptimizer


class TestQueryOptimizer:
    def test_recommend_path_bfs(self):
        opt = QueryOptimizer()
        strat = opt.recommend_strategy("path", estimated_depth=20)
        assert strat == opt.STRATEGY_BFS

    def test_recommend_path_short(self):
        opt = QueryOptimizer()
        strat = opt.recommend_strategy("path", estimated_depth=5)
        assert strat == opt.STRATEGY_SHORTEST_PATH

    def test_recommend_pattern(self):
        opt = QueryOptimizer()
        strat = opt.recommend_strategy("pattern")
        assert strat == opt.STRATEGY_PATTERN_MATCH

    def test_recommend_subgraph(self):
        opt = QueryOptimizer()
        strat = opt.recommend_strategy("subgraph")
        assert strat == opt.STRATEGY_SUBGRAPH

    def test_recommend_traverse_wide_bfs(self):
        opt = QueryOptimizer()
        strat = opt.recommend_strategy("traverse", estimated_fan_out=10, estimated_depth=11)
        assert strat == opt.STRATEGY_BFS

    def test_recommend_traverse_narrow_dfs(self):
        opt = QueryOptimizer()
        strat = opt.recommend_strategy("traverse", estimated_fan_out=2, estimated_depth=3)
        assert strat == opt.STRATEGY_DFS

    def test_estimate_cost_bfs(self):
        opt = QueryOptimizer()
        est = opt.estimate_cost(opt.STRATEGY_BFS, node_count=1000, edge_count=5000)
        assert est["strategy"] == opt.STRATEGY_BFS
        assert "estimated_nodes_visited" in est

    def test_estimate_cost_shortest_path(self):
        opt = QueryOptimizer()
        est = opt.estimate_cost(opt.STRATEGY_SHORTEST_PATH)
        assert est["strategy"] == opt.STRATEGY_SHORTEST_PATH

    def test_estimate_cost_pattern(self):
        opt = QueryOptimizer()
        est = opt.estimate_cost(opt.STRATEGY_PATTERN_MATCH)
        assert est["strategy"] == opt.STRATEGY_PATTERN_MATCH

    def test_estimate_cost_subgraph(self):
        opt = QueryOptimizer()
        est = opt.estimate_cost(opt.STRATEGY_SUBGRAPH)
        assert est["strategy"] == opt.STRATEGY_SUBGRAPH

    def test_should_cache_high_frequency(self):
        opt = QueryOptimizer()
        assert opt.should_cache("subgraph", frequency=3) is True

    def test_should_cache_low_frequency(self):
        opt = QueryOptimizer()
        assert opt.should_cache("path", frequency=1) is False

    def test_constant_names(self):
        opt = QueryOptimizer()
        assert opt.STRATEGY_BFS == "bfs"
        assert opt.STRATEGY_DFS == "dfs"
        assert opt.STRATEGY_SHORTEST_PATH == "shortest_path"
        assert opt.STRATEGY_PATTERN_MATCH == "pattern_match"
        assert opt.STRATEGY_SUBGRAPH == "subgraph"
