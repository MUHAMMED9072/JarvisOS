from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ads.architecture_designer import ArchitectureSpec
from app.ads.templates.code_templates import (
    AGENT_TEMPLATE,
    DOCUMENTATION_TEMPLATE,
    INTEGRATION_TEMPLATE,
    KNOWLEDGE_PACK_TEMPLATE,
    PIPELINE_TEMPLATE,
    PLUGIN_TEMPLATE,
    SKILL_TEMPLATE,
    TEST_SUITE_TEMPLATE,
    TOOL_TEMPLATE,
    WORKFLOW_TEMPLATE,
)
from app.ads.type_registry import ArtifactTypeRegistry


@dataclass
class GeneratedContent:
    """Result of content generation."""

    files: dict[str, str] = field(default_factory=dict)  # filename -> content
    manifest: dict[str, Any] = field(default_factory=dict)
    base_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": dict(self.files),
            "manifest": dict(self.manifest),
            "base_path": self.base_path,
        }


class ContentGenerator:
    """Generate source code, YAML, Markdown, or JSON from architecture specs.

    Uses template system with one template per artifact type.
    """

    # Map artifact type -> template
    TEMPLATES: dict[str, str] = {
        "Agent": AGENT_TEMPLATE,
        "Tool": TOOL_TEMPLATE,
        "Plugin": PLUGIN_TEMPLATE,
        "Skill": SKILL_TEMPLATE,
        "Workflow": WORKFLOW_TEMPLATE,
        "Pipeline": PIPELINE_TEMPLATE,
        "KnowledgePack": KNOWLEDGE_PACK_TEMPLATE,
        "TestSuite": TEST_SUITE_TEMPLATE,
        "Integration": INTEGRATION_TEMPLATE,
        "Documentation": DOCUMENTATION_TEMPLATE,
    }

    def __init__(
        self,
        registry: ArtifactTypeRegistry | None = None,
        output_dir: str = "app/ads/generated",
    ) -> None:
        self._registry = registry or ArtifactTypeRegistry()
        self._output_dir = Path(output_dir)

    def generate(self, spec: ArchitectureSpec) -> GeneratedContent:
        atype = spec.artifact_type
        template = self.TEMPLATES.get(atype)
        if template is None:
            template = AGENT_TEMPLATE

        content = GeneratedContent(base_path=str(self._output_dir / spec.name))

        # Generate main file
        filename, file_content = self._render_file(atype, spec, template)
        content.files[filename] = file_content

        # Generate manifest
        content.manifest = self._generate_manifest(spec)

        # Generate __init__.py for Python artifacts
        if atype in ("Agent", "Tool", "Plugin", "Skill", "Integration", "TestSuite"):
            content.files["__init__.py"] = ""

        return content

    def _render_file(
        self, atype: str, spec: ArchitectureSpec, template: str,
    ) -> tuple[str, str]:
        class_name = "".join(x.capitalize() for x in spec.name.split("_"))
        cap_names = [c["name"] for c in spec.components if c.get("type") == "capability"]
        capabilities = json.dumps(cap_names)
        description = spec.description.replace('"', '\\"')

        if atype == "Agent":
            content = template.format(
                class_name=class_name,
                name=spec.name,
                version="1.0.0",
                description=description,
                capabilities=capabilities,
            )
            return f"{spec.name}.py", content

        if atype == "Tool":
            tool_name = spec.name
            content = template.format(
                class_name=class_name,
                tool_name=tool_name,
                description=description,
            )
            return f"{spec.name}.py", content

        if atype == "Plugin":
            content = template.format(
                class_name=class_name,
                name=spec.name,
                version="1.0.0",
                description=description,
                capabilities=capabilities,
            )
            return f"{spec.name}.py", content

        if atype == "Skill":
            content = template.format(
                class_name=class_name,
                name=spec.name,
                version="1.0.0",
                description=description,
            )
            return f"{spec.name}.py", content

        if atype == "Workflow":
            steps_yaml = "\n".join(
                f"  - name: {c['name']}\n    action: execute" for c in spec.components
            ) or "  - name: default\n    action: execute"
            content = template.format(
                name=spec.name,
                version="1.0.0",
                description=description,
                steps=steps_yaml,
            )
            return f"{spec.name}.yaml", content

        if atype == "Pipeline":
            stages_yaml = "\n".join(
                f"  - name: {c['name']}\n    type: {c.get('type', 'task')}" for c in spec.components
            ) or "  - name: default\n    type: task"
            content = template.format(
                name=spec.name,
                version="1.0.0",
                description=description,
                stages=stages_yaml,
            )
            return f"{spec.name}.yaml", content

        if atype == "KnowledgePack":
            domain = spec.description.split(" ")[0] if spec.description else "general"
            content = template.format(
                name=spec.name,
                version="1.0.0",
                description=description,
                domain=domain,
            )
            return f"{spec.name}.json", content

        if atype == "TestSuite":
            test_name = spec.name.lower().replace("-", "_").replace(" ", "_")
            content = template.format(
                class_name=class_name,
                target=spec.name,
                test_name=test_name,
            )
            return f"test_{spec.name}.py", content

        if atype == "Integration":
            content = template.format(
                class_name=class_name,
                name=spec.name,
                version="1.0.0",
                description=description,
                capabilities=capabilities,
            )
            return f"{spec.name}.py", content

        if atype == "Documentation":
            content = template.format(
                name=spec.name,
                description=description,
                version="1.0.0",
            )
            return f"{spec.name}.md", content

        return f"{spec.name}.txt", f"# {spec.name}\n{description}"

    def _generate_manifest(self, spec: ArchitectureSpec) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "name": spec.name,
            "version": "1.0.0",
            "type": spec.artifact_type,
            "description": spec.description,
        }
        if spec.artifact_type in ("Agent", "Plugin", "Skill", "Integration"):
            cap_names = [c["name"] for c in spec.components if c.get("type") == "capability"]
            manifest["capabilities"] = cap_names
        if spec.dependencies:
            manifest["dependencies"] = list(spec.dependencies)
        return manifest

    def write(self, content: GeneratedContent) -> Path:
        """Write generated content to disk."""
        base = self._output_dir / Path(content.base_path).name
        base.mkdir(parents=True, exist_ok=True)
        for filename, file_content in content.files.items():
            path = base / filename
            path.write_text(file_content, encoding="utf-8")
        manifest_path = base / "manifest.json"
        manifest_path.write_text(json.dumps(content.manifest, indent=2), encoding="utf-8")
        return base

    def health(self) -> dict[str, Any]:
        return {"alive": True, "templates": len(self.TEMPLATES)}
