from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.ads.content_generator import GeneratedContent
from app.ads.type_registry import ArtifactTypeRegistry
from app.knowledge_graph.capability_registry import CapabilityRegistry
from app.knowledge_graph.store import GraphStore


@dataclass
class RegistrationResult:
    """Result of Knowledge Graph registration for an artifact."""

    artifact_name: str = ""
    entity_id: str = ""
    capabilities_registered: list[str] = field(default_factory=list)
    relationships_created: list[str] = field(default_factory=list)
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "entity_id": self.entity_id,
            "capabilities_registered": list(self.capabilities_registered),
            "relationships_created": list(self.relationships_created),
            "success": self.success,
            "error": self.error,
        }


class Registration:
    """Register artifacts in the Knowledge Graph."""

    def __init__(
        self,
        graph_store: GraphStore,
        capability_registry: CapabilityRegistry | None = None,
        type_registry: ArtifactTypeRegistry | None = None,
    ) -> None:
        self._store = graph_store
        self._cap_registry = capability_registry or CapabilityRegistry(graph_store)
        self._type_registry = type_registry or ArtifactTypeRegistry()

    def register(
        self,
        artifact_name: str,
        content: GeneratedContent,
    ) -> RegistrationResult:
        atype = content.manifest.get("type", "Agent")

        # Create entity in KG
        entity = self._store.create_entity(
            type=atype.lower(),
            name=artifact_name,
            properties={
                "manifest": str(content.manifest),
                "version": content.manifest.get("version", "1.0.0"),
                "type": atype,
                "description": content.manifest.get("description", ""),
                "installed_at": str(time.time()),
                "base_path": content.base_path,
            },
        )
        entity_id = entity.id

        # Register capabilities
        caps = content.manifest.get("capabilities", [])
        caps_registered: list[str] = []
        rels_created: list[str] = []
        for cap in caps:
            # Create capability entity if not exists
            existing = self._store.get_entity_by_name(cap)
            if not existing:
                cap_entity = self._store.create_entity(
                    type="capability",
                    name=cap,
                    properties={"description": f"Capability: {cap}"},
                )
                cap_id = cap_entity.id
            else:
                cap_id = existing[0].id

            # Create relationship
            self._store.create_relationship(
                type="uses",
                source_id=entity_id,
                target_id=cap_id,
                properties={"registered_at": str(time.time())},
            )
            caps_registered.append(cap)
            rels_created.append(f"{artifact_name} -> uses -> {cap}")

        return RegistrationResult(
            artifact_name=artifact_name,
            entity_id=entity_id,
            capabilities_registered=caps_registered,
            relationships_created=rels_created,
            success=True,
        )

    def unregister(self, artifact_name: str) -> bool:
        entities = self._store.get_entity_by_name(artifact_name)
        if not entities:
            return False
        return self._store.delete_entity(entities[0].id)

    def health(self) -> dict[str, Any]:
        return {"alive": True}
