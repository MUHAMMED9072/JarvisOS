from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.ads.content_generator import GeneratedContent
from app.knowledge_graph.store import GraphStore


@dataclass
class ArtifactVersion:
    version: str = ""
    artifact_name: str = ""
    previous_version: str = ""
    changelog: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    entity_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "artifact_name": self.artifact_name,
            "previous_version": self.previous_version,
            "changelog": list(self.changelog),
            "created_at": self.created_at,
            "entity_id": self.entity_id,
        }


@dataclass
class VersionResult:
    success: bool = True
    error: str = ""
    version: ArtifactVersion | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "error": self.error,
            "version": self.version.to_dict() if self.version else None,
        }


class VersionManager:
    """Create and manage artifact versions with changelog tracking."""

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    def create_initial_version(
        self, artifact_name: str, content: GeneratedContent,
    ) -> VersionResult:
        manifest = content.manifest
        version_str = manifest.get("version", "1.0.0")
        description = manifest.get("description", "")
        atype = manifest.get("type", "agent").lower()

        changelog = [
            f"Initial release v{version_str}",
            f"Type: {atype}",
            f"Description: {description}",
        ]
        caps = manifest.get("capabilities", [])
        if caps:
            changelog.append(f"Capabilities: {', '.join(caps)}")
        deps = manifest.get("dependencies", [])
        if deps:
            changelog.append(f"Dependencies: {', '.join(deps)}")

        entities = self._store.get_entity_by_name(artifact_name)
        if not entities:
            return VersionResult(
                success=False,
                error=f"Artifact '{artifact_name}' not registered in KG",
            )

        entity = entities[0]
        version_entity = self._store.create_entity(
            type="concept",
            name=f"{artifact_name}_v{version_str}",
            properties={
                "artifact_name": artifact_name,
                "version": version_str,
                "changelog": str(changelog),
                "created_at": str(time.time()),
                "entity_id": entity.id,
            },
        )

        self._store.create_relationship(
            type="references",
            source_id=version_entity.id,
            target_id=entity.id,
            properties={"relation": "version_of"},
        )

        av = ArtifactVersion(
            version=version_str,
            artifact_name=artifact_name,
            previous_version="",
            changelog=changelog,
            created_at=time.time(),
            entity_id=version_entity.id,
        )
        return VersionResult(success=True, version=av)

    def get_version(self, artifact_name: str, version: str = "") -> ArtifactVersion | None:
        search_name = f"{artifact_name}_v{version}" if version else ""
        if search_name:
            entities = self._store.get_entity_by_name(search_name)
            if entities:
                e = entities[0]
                return self._entity_to_version(e)
            return None
        # Return latest version
        all_versions = self.list_versions(artifact_name)
        return all_versions[-1] if all_versions else None

    def list_versions(self, artifact_name: str) -> list[ArtifactVersion]:
        entities = self._store.get_entities_by_type("concept")
        versions: list[ArtifactVersion] = []
        prefix = f"{artifact_name}_v"
        for e in entities:
            if not e.name.startswith(prefix):
                continue
            props = e.properties
            if props.get("artifact_name") == artifact_name:
                versions.append(self._entity_to_version(e))
        versions.sort(key=lambda v: v.created_at)
        return versions

    def _entity_to_version(self, entity: Any) -> ArtifactVersion:
        props = entity.properties
        import ast
        try:
            changelog = ast.literal_eval(props.get("changelog", "[]"))
        except (ValueError, SyntaxError):
            changelog = []
        return ArtifactVersion(
            version=props.get("version", ""),
            artifact_name=props.get("artifact_name", ""),
            previous_version=props.get("previous_version", ""),
            changelog=changelog,
            created_at=float(props.get("created_at", 0)),
            entity_id=entity.id,
        )

    def health(self) -> dict[str, Any]:
        return {"alive": True}
