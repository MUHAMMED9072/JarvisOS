from __future__ import annotations

import pytest

from app.knowledge_graph.store import GraphStore


@pytest.fixture
def graph_store(tmp_path) -> GraphStore:
    store = GraphStore(filename="test_knowledge_graph.json")
    store.path = tmp_path / "test_knowledge_graph.json"
    store.clear()
    # Ensure the file exists after clear
    store.save()
    return store
