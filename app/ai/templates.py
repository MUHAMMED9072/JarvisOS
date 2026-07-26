from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


class PromptTemplateError(Exception):
    """Base exception for prompt template errors."""


class PromptTemplateValidationError(PromptTemplateError):
    """Raised when a template definition is invalid."""


class PromptTemplateRenderError(PromptTemplateError):
    """Raised when template rendering fails."""


class DuplicateTemplateError(PromptTemplateError):
    """Raised when registering a template with a name that already exists."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptVariable:
    """A variable in a prompt template."""
    name: str
    description: str = ""
    default: str | None = None
    required: bool = True
    metadata: dict | None = None


@dataclass(frozen=True)
class PromptTemplate:
    """A reusable prompt template with variables."""
    name: str
    description: str
    template: str
    variables: list[PromptVariable] = field(default_factory=list)
    metadata: dict | None = None


@dataclass(frozen=True)
class PromptRenderResult:
    """The result of rendering a prompt template."""
    text: str
    template_name: str
    variables_used: frozenset[str]
    render_duration_ms: float
    metadata: dict | None = None


@dataclass(frozen=True)
class PromptValidationResult:
    """The result of validating a template and its variables."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Variable extraction
# ---------------------------------------------------------------------------

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _extract_variable_names(template: str) -> list[str]:
    """Return all variable names found in *template*."""
    return _VARIABLE_PATTERN.findall(template)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_template(template: PromptTemplate) -> PromptValidationResult:
    """Validate a ``PromptTemplate`` definition."""
    errors: list[str] = []
    warnings: list[str] = []

    if not template.name or not isinstance(template.name, str):
        errors.append("Template name must be a non-empty string")
    if not template.template or not isinstance(template.template, str):
        errors.append("Template body must be a non-empty string")
    if template.metadata is not None and not isinstance(template.metadata, dict):
        errors.append("Template metadata must be a dict or None")

    used_vars = _extract_variable_names(template.template)
    declared_names = {v.name for v in template.variables}

    seen: set[str] = set()
    for v in template.variables:
        if not v.name or not isinstance(v.name, str):
            errors.append("Variable name must be a non-empty string")
            continue
        if v.name in seen:
            errors.append(f"Duplicate variable name: {v.name!r}")
        seen.add(v.name)
        if v.metadata is not None and not isinstance(v.metadata, dict):
            errors.append(f"Variable {v.name!r} metadata must be a dict or None")

    for used in used_vars:
        if used not in declared_names:
            errors.append(
                f"Variable {used!r} is used in the template but not declared"
            )

    for v in template.variables:
        if v.required and v.name not in used_vars:
            warnings.append(
                f"Variable {v.name!r} is declared as required "
                f"but not used in the template"
            )

    return PromptValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_template(
    template: PromptTemplate,
    variables: dict[str, str] | None = None,
) -> PromptRenderResult:
    """Render *template* with the supplied *variables*.

    Raises
    ------
    PromptTemplateValidationError
        If the template definition is invalid.
    PromptTemplateRenderError
        If required variables are missing.
    """
    validation = validate_template(template)
    if not validation.valid:
        raise PromptTemplateValidationError(
            f"Cannot render invalid template {template.name!r}: "
            f"{'; '.join(validation.errors)}"
        )

    resolved: dict[str, str] = {}
    errors: list[str] = []

    for var in template.variables:
        if var.name in (variables or {}):
            resolved[var.name] = variables[var.name]
        elif var.default is not None:
            resolved[var.name] = var.default
        elif var.required:
            errors.append(f"Required variable {var.name!r} is missing")

    if errors:
        raise PromptTemplateRenderError(
            f"Cannot render template {template.name!r}: "
            f"{'; '.join(errors)}"
        )

    start = time.monotonic()
    result_text = template.template
    for name, value in resolved.items():
        result_text = result_text.replace("{{" + name + "}}", value)
    duration = (time.monotonic() - start) * 1000

    return PromptRenderResult(
        text=result_text,
        template_name=template.name,
        variables_used=frozenset(resolved.keys()),
        render_duration_ms=duration,
        metadata=template.metadata,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PromptTemplateRegistry:
    """A thread-safe registry for ``PromptTemplate`` instances."""

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}
        self._lock = Lock()

    def register(self, template: PromptTemplate) -> None:
        """Register *template*.

        Raises ``DuplicateTemplateError`` if a template with the
        same ``name`` is already registered.
        """
        validation = validate_template(template)
        if not validation.valid:
            raise PromptTemplateValidationError(
                f"Cannot register invalid template {template.name!r}: "
                f"{'; '.join(validation.errors)}"
            )
        with self._lock:
            if template.name in self._templates:
                raise DuplicateTemplateError(
                    f"A template named {template.name!r} is already registered"
                )
            self._templates[template.name] = template

    def unregister(self, name: str) -> bool:
        """Remove the template identified by *name*."""
        with self._lock:
            return self._templates.pop(name, None) is not None

    def get(self, name: str) -> PromptTemplate | None:
        """Return the template with *name*, or ``None``."""
        with self._lock:
            return self._templates.get(name)

    def has(self, name: str) -> bool:
        """Return ``True`` if a template named *name* is registered."""
        with self._lock:
            return name in self._templates

    def list(self) -> list[PromptTemplate]:
        """Return every registered template (ordered by registration)."""
        with self._lock:
            return list(self._templates.values())

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._templates)
