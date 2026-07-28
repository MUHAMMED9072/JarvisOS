from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


AMBIGUITY_PATTERNS = [
    (r"\b(it|this|that|something)\b", "Vague pronoun"),
    (r"\b(maybe|perhaps|possibly|might)\b", "Uncertain language"),
    (r"\b(some|various|multiple|many|lots)\b", "Vague quantity"),
    (r"\b(quick|fast|efficient|good|better|best)\b", "Subjective qualifier"),
    (r"\b(etc|etc\.|and so on)\b", "Incomplete specification"),
    (r"\?", "Question in requirement"),
    (r"\b(ideally|preferably|would like|want)\b", "Desire not requirement"),
    (r"\b(after|eventually|sometime|later)\b", "Unclear timing"),
]


@dataclass
class AmbiguityFlag:
    text: str = ""
    reason: str = ""
    pattern: str = ""


@dataclass
class StructuredRequirement:
    """A single parsed requirement from a user request."""

    description: str = ""
    artifact_type: str = "Agent"
    capabilities_needed: list[str] = field(default_factory=list)
    priority: str = "medium"
    constraints: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class RequirementsDocument:
    """Full structured output of the requirements analysis stage."""

    raw_request: str = ""
    artifact_type: str = "Agent"
    name: str = ""
    description: str = ""
    requirements: list[StructuredRequirement] = field(default_factory=list)
    capabilities_needed: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    ambiguity_flags: list[AmbiguityFlag] = field(default_factory=list)

    def is_ambiguous(self) -> bool:
        return len(self.ambiguity_flags) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_request": self.raw_request,
            "artifact_type": self.artifact_type,
            "name": self.name,
            "description": self.description,
            "requirements": [r.__dict__ for r in self.requirements],
            "capabilities_needed": list(self.capabilities_needed),
            "constraints": list(self.constraints),
            "dependencies": list(self.dependencies),
            "ambiguity_flags": [a.__dict__ for a in self.ambiguity_flags],
            "is_ambiguous": self.is_ambiguous(),
        }


class RequirementsAnalyzer:
    """Parse user request into structured requirements.

    Uses keyword heuristics to identify artifact type, capabilities,
    constraints, and ambiguity.  In production this would leverage the
    LLM reasoning pipeline from Phase 3.
    """

    # Simple keyword -> artifact type mapping
    TYPE_KEYWORDS: dict[str, str] = {
        "agent": "Agent",
        "tool": "Tool",
        "plugin": "Plugin",
        "skill": "Skill",
        "workflow": "Workflow",
        "pipeline": "Pipeline",
        "knowledge": "KnowledgePack",
        "test": "TestSuite",
        "integration": "Integration",
        "doc": "Documentation",
        "documentation": "Documentation",
    }

    # Keyword -> capability
    CAPABILITY_KEYWORDS: dict[str, str] = {
        "scrape": "web_scraping",
        "web": "web_scraping",
        "crawl": "web_scraping",
        "search": "web_search",
        "analyze": "data_analysis",
        "report": "reporting",
        "monitor": "monitoring",
        "alert": "alerting",
        "deploy": "deployment",
        "build": "build",
        "test": "testing",
        "communicate": "communication",
        "chat": "conversation",
        "translate": "translation",
        "summarize": "summarization",
        "extract": "data_extraction",
        "transform": "data_transformation",
        "load": "data_loading",
        "store": "data_storage",
        "visualize": "visualization",
        "train": "ml_training",
        "predict": "ml_prediction",
    }

    def analyze(self, request: str) -> RequirementsDocument:
        request_lower = request.lower()
        doc = RequirementsDocument(raw_request=request)

        # Detect artifact type
        doc.artifact_type = self._detect_type(request_lower)

        # Extract name
        doc.name = self._extract_name(request, doc.artifact_type)

        # Extract description
        doc.description = request

        # Extract capabilities
        doc.capabilities_needed = self._detect_capabilities(request_lower)

        # Extract constraints
        doc.constraints = self._detect_constraints(request)

        # Detect ambiguity
        doc.ambiguity_flags = self._detect_ambiguity(request)

        # Build structured requirements
        req = StructuredRequirement(
            description=request,
            artifact_type=doc.artifact_type,
            capabilities_needed=list(doc.capabilities_needed),
            constraints=list(doc.constraints),
        )
        doc.requirements = [req]

        return doc

    def _detect_type(self, text: str) -> str:
        for keyword, atype in self.TYPE_KEYWORDS.items():
            if keyword in text:
                return atype
        return "Agent"

    def _extract_name(self, request: str, artifact_type: str) -> str:
        patterns = [
            r"(?:called|named)\s+['\"]?(\w+)['\"]?",
            r"(?:a|an)\s+(?:\w+\s+)?(?:agent|tool|plugin|skill)\s+(?:called|named)\s+['\"]?(\w+)['\"]?",
        ]
        for pat in patterns:
            m = re.search(pat, request, re.IGNORECASE)
            if m:
                return m.group(1)
        return f"{artifact_type.lower()}_{len(request) % 1000}"

    def _detect_capabilities(self, text: str) -> list[str]:
        caps: list[str] = []
        for keyword, cap in self.CAPABILITY_KEYWORDS.items():
            if keyword in text and cap not in caps:
                caps.append(cap)
        return caps

    def _detect_constraints(self, request: str) -> list[str]:
        constraints: list[str] = []
        constraint_patterns = [
            (r"(?:must|should|shall|need to)\s+(\w[\w\s]*)", "positive"),
            (r"(?:must not|should not|shall not|cannot)\s+(\w[\w\s]*)", "negative"),
        ]
        for pat, _kind in constraint_patterns:
            for m in re.finditer(pat, request, re.IGNORECASE):
                constraint = m.group(1).strip()
                if constraint and len(constraint) > 2:
                    constraints.append(constraint)
        return constraints

    def _detect_ambiguity(self, request: str) -> list[AmbiguityFlag]:
        flags: list[AmbiguityFlag] = []
        for pattern, reason in AMBIGUITY_PATTERNS:
            for m in re.finditer(pattern, request, re.IGNORECASE):
                flags.append(AmbiguityFlag(
                    text=m.group(0),
                    reason=reason,
                    pattern=pattern,
                ))
        return flags

    def health(self) -> dict[str, Any]:
        return {"alive": True, "type_keywords": len(self.TYPE_KEYWORDS)}
