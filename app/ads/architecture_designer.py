from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ads.gap_detector import GapReport
from app.ads.requirements import RequirementsDocument
from app.ads.type_registry import ArtifactTypeRegistry


@dataclass
class ArchitectureSpec:
    """Complete architecture specification for a new artifact."""

    name: str = ""
    artifact_type: str = "Agent"
    description: str = ""
    components: list[dict[str, Any]] = field(default_factory=list)
    interfaces: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    data_flow: list[dict[str, Any]] = field(default_factory=list)
    security_considerations: list[str] = field(default_factory=list)
    design_rationale: str = ""
    alternative_score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "artifact_type": self.artifact_type,
            "description": self.description,
            "components": list(self.components),
            "interfaces": list(self.interfaces),
            "dependencies": list(self.dependencies),
            "data_flow": list(self.data_flow),
            "security_considerations": list(self.security_considerations),
            "design_rationale": self.design_rationale,
            "alternative_score": self.alternative_score,
        }


class ArchitectureDesigner:
    """Produce architecture specification from gap report and requirements."""

    def __init__(
        self,
        registry: ArtifactTypeRegistry | None = None,
    ) -> None:
        self._registry = registry or ArtifactTypeRegistry()

    def design(
        self,
        requirements: RequirementsDocument,
        gap_report: GapReport,
    ) -> list[ArchitectureSpec]:
        """Generate architecture specifications.

        Returns ranked alternatives (first = highest ranked).
        """
        base = self._build_base_spec(requirements, gap_report)
        alternatives = [base]

        # Generate alternative if gaps exist
        if gap_report.has_gaps():
            alt = self._build_alternative(base, gap_report)
            alternatives.append(alt)

        # Rank by score (descending)
        alternatives.sort(key=lambda x: x.alternative_score, reverse=True)
        return alternatives

    def _build_base_spec(
        self,
        requirements: RequirementsDocument,
        gap_report: GapReport,
    ) -> ArchitectureSpec:
        atype = self._registry.get(requirements.artifact_type)
        atype_name = atype.name if atype else requirements.artifact_type

        components = self._generate_components(requirements, atype_name)
        interfaces = self._generate_interfaces(components)
        deps = list(requirements.dependencies)
        data_flow = self._generate_data_flow(components, interfaces)
        security = self._generate_security(requirements)

        return ArchitectureSpec(
            name=requirements.name,
            artifact_type=atype_name,
            description=requirements.description,
            components=components,
            interfaces=interfaces,
            dependencies=deps,
            data_flow=data_flow,
            security_considerations=security,
            design_rationale=f"Standard architecture for {atype_name}",
            alternative_score=1.0,
        )

    def _build_alternative(
        self, base: ArchitectureSpec, gap_report: GapReport,
    ) -> ArchitectureSpec:
        alt = ArchitectureSpec(
            name=base.name,
            artifact_type=base.artifact_type,
            description=f"{base.description} [Alternative design]",
            components=list(base.components),
            interfaces=list(base.interfaces),
            dependencies=list(base.dependencies),
            data_flow=list(base.data_flow),
            security_considerations=list(base.security_considerations),
            design_rationale=(
                f"Alternative addressing gaps: {', '.join(gap_report.missing_capabilities)}"
            ),
            alternative_score=0.85,
        )
        if gap_report.combination_opportunities:
            for combo in gap_report.combination_opportunities:
                alt.components.append({
                    "name": f"combined_{combo['target_capability']}",
                    "type": "combination",
                    "description": combo["suggestion"],
                })
        return alt

    def _generate_components(
        self, requirements: RequirementsDocument, atype_name: str,
    ) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []
        comp_map: dict[str, str] = {
            "Agent": "CoreAgent",
            "Tool": "ToolExecutor",
            "Plugin": "PluginHost",
            "Skill": "SkillEngine",
            "Workflow": "WorkflowOrchestrator",
            "Pipeline": "PipelineRunner",
            "KnowledgePack": "KnowledgeBase",
            "TestSuite": "TestRunner",
            "Integration": "IntegrationAdapter",
            "Documentation": "DocGenerator",
        }
        main_comp = comp_map.get(atype_name, "CoreComponent")
        components.append({
            "name": main_comp,
            "type": "primary",
            "description": f"Main component for {atype_name} '{requirements.name}'",
        })
        for cap in requirements.capabilities_needed:
            components.append({
                "name": f"cap_{cap}",
                "type": "capability",
                "description": f"Handles {cap}",
            })
        return components

    def _generate_interfaces(
        self, components: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        interfaces: list[dict[str, Any]] = []
        for comp in components:
            interfaces.append({
                "name": f"{comp['name']}_api",
                "component": comp["name"],
                "methods": ["execute", "status", "configure"],
            })
        if len(components) > 1:
            interfaces.append({
                "name": "inter_component_bus",
                "component": "system",
                "methods": ["send", "receive", "subscribe"],
            })
        return interfaces

    def _generate_data_flow(
        self, components: list[dict[str, Any]],
        interfaces: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        flow: list[dict[str, Any]] = []
        flow.append({
            "from": "input",
            "to": components[0]["name"] if components else "core",
            "description": "Request enters the system",
        })
        for i in range(len(components) - 1):
            flow.append({
                "from": components[i]["name"],
                "to": components[i + 1]["name"],
                "description": f"Data flows from {components[i]['name']} to {components[i + 1]['name']}",
            })
        flow.append({
            "from": components[-1]["name"] if components else "core",
            "to": "output",
            "description": "Result returned to caller",
        })
        return flow

    def _generate_security(
        self, requirements: RequirementsDocument,
    ) -> list[str]:
        security: list[str] = []
        constraints_lower = [c.lower() for c in requirements.constraints]
        if any("network" in c for c in constraints_lower):
            security.append("Network access must be restricted to approved endpoints")
        if any("auth" in c or "authentication" in c for c in constraints_lower):
            security.append("Authentication required for all API endpoints")
        security.append("All inputs must be validated before processing")
        security.append("Least privilege principle for all permissions")
        return security

    def health(self) -> dict[str, Any]:
        return {"alive": True}
