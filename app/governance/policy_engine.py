from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.governance.policy_registry import (
    PolicyAction,
    PolicyEvaluation,
    PolicyRegistry,
    PolicyScope,
)


@dataclass
class PolicyDecision:
    action: PolicyAction = PolicyAction.DENY
    reason: str = "No applicable policy"
    evaluations: list[PolicyEvaluation] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    evaluated_at: float = field(default_factory=time.time)

    @property
    def allowed(self) -> bool:
        return self.action == PolicyAction.ALLOW

    @property
    def denied(self) -> bool:
        return self.action == PolicyAction.DENY

    @property
    def flagged(self) -> bool:
        return self.action == PolicyAction.FLAG

    @property
    def requires_approval(self) -> bool:
        return self.action == PolicyAction.REQUIRE_APPROVAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "evaluations": [e.to_dict() for e in self.evaluations],
            "allowed": self.allowed,
            "denied": self.denied,
            "flagged": self.flagged,
            "requires_approval": self.requires_approval,
            "evaluated_at": self.evaluated_at,
        }


class PolicyEngine:
    """Evaluates policies from the PolicyRegistry against a context dict.

    Policy evaluation chain:
      1. Collect all applicable policies (by scope match and enabled)
      2. Sort by priority (highest first)
      3. For each policy, evaluate its rules in order
      4. First matching rule determines the policy's action
      5. Final action: if any policy DENIES, the result is DENY.
         Otherwise the highest-priority non-ALLOW action wins.
         If all policies ALLOW, the result is ALLOW.

    Thread-safe.
    """

    def __init__(self, registry: PolicyRegistry | None = None) -> None:
        self._registry = registry or PolicyRegistry()
        self._lock = threading.RLock()
        self._evaluation_count: int = 0

    @property
    def registry(self) -> PolicyRegistry:
        return self._registry

    def evaluate(self, context: dict[str, Any]) -> PolicyDecision:
        with self._lock:
            self._evaluation_count += 1
            scope_str = context.get("scope", "global")
            scope = self._parse_scope(scope_str)

            policies = self._registry.list_policies(enabled_only=True)
            applicable = [p for p in policies if self._scope_matches(p.scope, scope)]

            evaluations: list[PolicyEvaluation] = []
            final_action: PolicyAction = PolicyAction.ALLOW
            final_reason = "All policies allow this operation"

            for policy in applicable:
                action, reason = self._evaluate_policy(policy, context)
                evaluations.append(PolicyEvaluation(
                    policy_id=policy.id, action=action, reason=reason,
                ))
                if action == PolicyAction.DENY:
                    final_action = PolicyAction.DENY
                    final_reason = reason
                    break
                if action == PolicyAction.REQUIRE_APPROVAL and final_action != PolicyAction.REQUIRE_APPROVAL:
                    final_action = PolicyAction.REQUIRE_APPROVAL
                    final_reason = reason
                if action == PolicyAction.FLAG and final_action == PolicyAction.ALLOW:
                    final_action = PolicyAction.FLAG
                    final_reason = reason

            return PolicyDecision(
                action=final_action,
                reason=final_reason,
                evaluations=evaluations,
                context=context,
            )

    def _evaluate_policy(
        self,
        policy: Any,
        context: dict[str, Any],
    ) -> tuple[PolicyAction, str]:
        for rule in policy.rules:
            if self._evaluate_condition(rule.condition, context):
                return rule.action, rule.reason or f"Policy '{policy.name}' rule matched"
        return PolicyAction.ALLOW, f"Policy '{policy.name}' no rules matched"

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        if not condition:
            return True
        parts = condition.split()
        if len(parts) < 3:
            return True

        field = parts[0]
        op = parts[1]
        value_str = " ".join(parts[2:])

        actual = self._resolve_field(field, context)
        if actual is None:
            return op == "!="

        try:
            value = self._coerce(value_str, type(actual))
        except (ValueError, TypeError):
            value = value_str

        if op == "==":
            return actual == value
        if op == "!=":
            return actual != value
        if op == ">":
            return float(actual) > float(value)
        if op == ">=":
            return float(actual) >= float(value)
        if op == "<":
            return float(actual) < float(value)
        if op == "<=":
            return float(actual) <= float(value)
        if op == "in":
            return str(actual) in str(value).split(",")
        if op == "not_in":
            return str(actual) not in str(value).split(",")
        return True

    def _resolve_field(self, field: str, context: dict[str, Any]) -> Any:
        parts = field.split(".")
        current: Any = context
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _coerce(self, value: str, target_type: type) -> Any:
        if target_type == bool:
            return value.lower() in ("true", "1", "yes")
        if target_type == int:
            return int(value)
        if target_type == float:
            return float(value)
        return value

    def _parse_scope(self, scope_str: str) -> PolicyScope | None:
        try:
            return PolicyScope(scope_str)
        except ValueError:
            return None

    def _scope_matches(self, policy_scope: PolicyScope, target_scope: PolicyScope | None) -> bool:
        if target_scope is None:
            return False
        if policy_scope == PolicyScope.GLOBAL:
            return True
        return policy_scope == target_scope

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "policies_registered": self._registry.count(),
                "evaluations_performed": self._evaluation_count,
            }

    def health(self) -> dict[str, Any]:
        stats = self.get_stats()
        return {
            "alive": True,
            "policies": stats["policies_registered"],
            "evaluations": stats["evaluations_performed"],
        }
