from __future__ import annotations

import pytest

from app.knowledge_graph.store import GraphStore


@pytest.fixture
def graph_store(tmp_path) -> GraphStore:
    store = GraphStore(filename="test_knowledge_graph.json")
    store.path = tmp_path / "test_knowledge_graph.json"
    store.clear()
    store.save()
    return store


@pytest.fixture
def supervisor(graph_store) -> "Supervisor":
    from app.intelligence.supervisor import Supervisor
    return Supervisor(graph_store)
