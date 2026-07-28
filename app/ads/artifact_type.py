from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Pipeline stages ─────────────────────────────────────────────────

ADS_STAGES = [
    "requirements_analysis",
    "capability_analysis",
    "gap_detection",
    "architecture_design",
    "content_generation",
    "test_generation",
    "sandbox_execution",
    "benchmark",
    "security_review",
    "performance_review",
    "governance_check",
    "approval",
    "installation",
    "registration",
    "versioning",
    "metrics_collection",
    "learning_loop",
]

# ── Artifact type definitions ───────────────────────────────────────

AGENT_CLASSES = {
    "Agent": "app.agents.base.Agent",
    "Tool": "app.agents.types.ToolAgent",
    "Plugin": "app.agents.base.Agent",
    "Skill": "app.agents.base.Agent",
    "Workflow": None,
    "Pipeline": None,
    "KnowledgePack": None,
    "TestSuite": None,
    "Integration": "app.agents.base.Agent",
    "Documentation": None,
}

# Per-type configuration: which stages to run
ARTIFACT_TYPE_STAGES: dict[str, list[str]] = {
    "Agent": ADS_STAGES,
    "Tool": ADS_STAGES,
    "Plugin": ADS_STAGES,
    "Skill": ADS_STAGES,
    "Workflow": [
        "requirements_analysis", "capability_analysis", "architecture_design",
        "content_generation", "test_generation", "sandbox_execution",
        "governance_check", "approval", "installation", "registration",
        "versioning", "learning_loop",
    ],
    "Pipeline": [
        "requirements_analysis", "capability_analysis", "architecture_design",
        "content_generation", "test_generation", "sandbox_execution",
        "governance_check", "approval", "installation", "registration",
        "versioning", "learning_loop",
    ],
    "KnowledgePack": [
        "requirements_analysis", "capability_analysis", "architecture_design",
        "content_generation", "test_generation", "sandbox_execution",
        "governance_check", "approval", "installation", "registration",
        "versioning", "learning_loop",
    ],
    "TestSuite": [
        "requirements_analysis", "capability_analysis", "architecture_design",
        "content_generation", "sandbox_execution",
        "governance_check", "approval", "installation", "registration",
        "versioning",
    ],
    "Integration": ADS_STAGES,
    "Documentation": [
        "requirements_analysis", "architecture_design",
        "content_generation", "governance_check", "approval",
        "installation", "registration", "versioning",
    ],
}

# Base class mapping
ARTIFACT_BASE_CLASSES: dict[str, str | None] = {
    "Agent": "app.agents.base.Agent",
    "Tool": "app.agents.types.ToolAgent",
    "Plugin": "app.agents.base.Agent",
    "Skill": "app.agents.base.Agent",
    "Workflow": None,
    "Pipeline": None,
    "KnowledgePack": None,
    "TestSuite": None,
    "Integration": "app.agents.base.Agent",
    "Documentation": None,
}

# Manifest JSON Schemas
MANIFEST_SCHEMAS: dict[str, dict[str, Any]] = {
    "Agent": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "capabilities"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["Agent"]},
            "description": {"type": "string"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "dependencies": {"type": "array", "items": {"type": "string"}},
        },
    },
    "Tool": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "tool_name"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["Tool"]},
            "tool_name": {"type": "string"},
            "description": {"type": "string"},
            "commands": {"type": "array", "items": {"type": "string"}},
        },
    },
    "Plugin": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "entry_point"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["Plugin"]},
            "entry_point": {"type": "string"},
            "dependencies": {"type": "array", "items": {"type": "string"}},
        },
    },
    "Skill": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "capabilities"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["Skill"]},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "prerequisites": {"type": "array", "items": {"type": "string"}},
        },
    },
    "Workflow": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "steps"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["Workflow"]},
            "steps": {"type": "array", "items": {"type": "object"}},
            "triggers": {"type": "array", "items": {"type": "string"}},
        },
    },
    "Pipeline": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "stages"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["Pipeline"]},
            "stages": {"type": "array", "items": {"type": "object"}},
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        },
    },
    "KnowledgePack": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "domain"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["KnowledgePack"]},
            "domain": {"type": "string"},
            "entries": {"type": "array", "items": {"type": "object"}},
        },
    },
    "TestSuite": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "target"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["TestSuite"]},
            "target": {"type": "string"},
            "framework": {"type": "string"},
            "tests": {"type": "array", "items": {"type": "object"}},
        },
    },
    "Integration": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "integrations"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["Integration"]},
            "integrations": {"type": "array", "items": {"type": "string"}},
            "protocol": {"type": "string"},
        },
    },
    "Documentation": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "version", "type", "format"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "type": {"type": "string", "enum": ["Documentation"]},
            "format": {"type": "string", "enum": ["markdown", "html", "rst"]},
            "pages": {"type": "array", "items": {"type": "object"}},
        },
    },
}


@dataclass
class ArtifactType:
    """Definition of an artifact type in the ADS system."""

    name: str
    description: str = ""
    stages: list[str] = field(default_factory=list)
    base_class: str | None = None
    manifest_schema: dict[str, Any] = field(default_factory=dict)
    output_extension: str = ".py"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "stages": list(self.stages),
            "base_class": self.base_class,
            "manifest_schema": dict(self.manifest_schema),
            "output_extension": self.output_extension,
        }


BUILTIN_ARTIFACT_TYPES: dict[str, ArtifactType] = {
    "Agent": ArtifactType(
        name="Agent",
        description="An AI agent with capabilities and lifecycle management",
        stages=ARTIFACT_TYPE_STAGES["Agent"],
        base_class=ARTIFACT_BASE_CLASSES["Agent"],
        manifest_schema=MANIFEST_SCHEMAS["Agent"],
        output_extension=".py",
    ),
    "Tool": ArtifactType(
        name="Tool",
        description="A tool with specific commands and functionality",
        stages=ARTIFACT_TYPE_STAGES["Tool"],
        base_class=ARTIFACT_BASE_CLASSES["Tool"],
        manifest_schema=MANIFEST_SCHEMAS["Tool"],
        output_extension=".py",
    ),
    "Plugin": ArtifactType(
        name="Plugin",
        description="A plugin or extension for the system",
        stages=ARTIFACT_TYPE_STAGES["Plugin"],
        base_class=ARTIFACT_BASE_CLASSES["Plugin"],
        manifest_schema=MANIFEST_SCHEMAS["Plugin"],
        output_extension=".py",
    ),
    "Skill": ArtifactType(
        name="Skill",
        description="A skill or capability bundle",
        stages=ARTIFACT_TYPE_STAGES["Skill"],
        base_class=ARTIFACT_BASE_CLASSES["Skill"],
        manifest_schema=MANIFEST_SCHEMAS["Skill"],
        output_extension=".py",
    ),
    "Workflow": ArtifactType(
        name="Workflow",
        description="A YAML-based workflow definition",
        stages=ARTIFACT_TYPE_STAGES["Workflow"],
        base_class=None,
        manifest_schema=MANIFEST_SCHEMAS["Workflow"],
        output_extension=".yaml",
    ),
    "Pipeline": ArtifactType(
        name="Pipeline",
        description="A processing pipeline with chained stages",
        stages=ARTIFACT_TYPE_STAGES["Pipeline"],
        base_class=None,
        manifest_schema=MANIFEST_SCHEMAS["Pipeline"],
        output_extension=".yaml",
    ),
    "KnowledgePack": ArtifactType(
        name="KnowledgePack",
        description="A knowledge pack for a specific domain",
        stages=ARTIFACT_TYPE_STAGES["KnowledgePack"],
        base_class=None,
        manifest_schema=MANIFEST_SCHEMAS["KnowledgePack"],
        output_extension=".json",
    ),
    "TestSuite": ArtifactType(
        name="TestSuite",
        description="A test suite targeting a specific artifact",
        stages=ARTIFACT_TYPE_STAGES["TestSuite"],
        base_class=None,
        manifest_schema=MANIFEST_SCHEMAS["TestSuite"],
        output_extension=".py",
    ),
    "Integration": ArtifactType(
        name="Integration",
        description="An integration connecting two or more systems",
        stages=ARTIFACT_TYPE_STAGES["Integration"],
        base_class=ARTIFACT_BASE_CLASSES["Integration"],
        manifest_schema=MANIFEST_SCHEMAS["Integration"],
        output_extension=".py",
    ),
    "Documentation": ArtifactType(
        name="Documentation",
        description="Documentation in Markdown, HTML, or RST format",
        stages=ARTIFACT_TYPE_STAGES["Documentation"],
        base_class=None,
        manifest_schema=MANIFEST_SCHEMAS["Documentation"],
        output_extension=".md",
    ),
}
