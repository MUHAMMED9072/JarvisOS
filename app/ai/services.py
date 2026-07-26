from __future__ import annotations

from .planning import (
    Plan,
    PlanValidationResult,
    parse_plan,
    validate_plan,
)
from .reasoning import (
    ReasoningChain,
    ReasoningValidationResult,
    parse_reasoning,
    validate_reasoning,
)
from .structured import (
    OutputParseError,
    OutputValidationError,
    SchemaValidationError,
    StructuredResult,
    StructuredSchema,
    parse_structured_output,
    validate_structured_schema,
)


class StructuredService:
    """Service wrapper for structured output parsing and validation."""

    def parse(
        self, raw_text: str, schema: StructuredSchema,
    ) -> StructuredResult:
        return parse_structured_output(raw_text, schema)

    def create_schema(
        self, name: str, schema: dict, metadata: dict | None = None,
    ) -> StructuredSchema:
        s = StructuredSchema(name=name, schema=schema, metadata=metadata)
        validate_structured_schema(s)
        return s

    def validate(self, schema: StructuredSchema) -> None:
        validate_structured_schema(schema)


class PlanningService:
    """Service wrapper for planning capabilities."""

    def parse(self, data: dict, provider: str = "", model: str = "") -> Plan:
        return parse_plan(data, provider=provider, model=model)

    def validate(self, plan: Plan) -> PlanValidationResult:
        return validate_plan(plan)


class ReasoningService:
    """Service wrapper for reasoning capabilities."""

    def parse(
        self, data: dict, provider: str = "", model: str = "",
    ) -> ReasoningChain:
        return parse_reasoning(data, provider=provider, model=model)

    def validate(
        self, chain: ReasoningChain,
    ) -> ReasoningValidationResult:
        return validate_reasoning(chain)
