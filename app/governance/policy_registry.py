from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyScope(Enum):
    SYSTEM = "system"
    AGENT = "agent"
    ARTIFACT = "artifact"
    USER = "user"
    GLOBAL = "global"


class PolicyAction(Enum):
    ALLOW = "allow"
    DENY = "deny"
    FLAG = "flag"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class PolicyRule:
    condition: str = ""
    action: PolicyAction = PolicyAction.DENY
    reason: str = ""
    severity: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "action": self.action.value,
            "reason": self.reason,
            "severity": self.severity,
        }


@dataclass
class Policy:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    description: str = ""
    scope: PolicyScope = PolicyScope.GLOBAL
    rules: list[PolicyRule] = field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scope": self.scope.value,
            "rules": [r.to_dict() for r in self.rules],
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class PolicyEvaluation:
    def __init__(self, policy_id: str, action: PolicyAction, reason: str) -> None:
        self.policy_id = policy_id
        self.action = action
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "action": self.action.value,
            "reason": self.reason,
        }


class PolicyRegistry:
    """Thread-safe registry for policies with CRUD operations."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._policies: dict[str, Policy] = {}

    def register(self, policy: Policy) -> str:
        with self._lock:
            self._policies[policy.id] = policy
            return policy.id

    def get(self, policy_id: str) -> Policy | None:
        with self._lock:
            return self._policies.get(policy_id)

    def get_by_name(self, name: str) -> Policy | None:
        with self._lock:
            for p in self._policies.values():
                if p.name == name:
                    return p
            return None

    def update(self, policy: Policy) -> bool:
        with self._lock:
            if policy.id not in self._policies:
                return False
            policy.updated_at = time.time()
            self._policies[policy.id] = policy
            return True

    def delete(self, policy_id: str) -> bool:
        with self._lock:
            if policy_id in self._policies:
                del self._policies[policy_id]
                return True
            return False

    def list_policies(
        self,
        scope: PolicyScope | None = None,
        enabled_only: bool = False,
    ) -> list[Policy]:
        with self._lock:
            result = list(self._policies.values())
            if scope:
                result = [p for p in result if p.scope == scope]
            if enabled_only:
                result = [p for p in result if p.enabled]
            return sorted(result, key=lambda p: p.priority, reverse=True)

    def count(self) -> int:
        with self._lock:
            return len(self._policies)

    def clear(self) -> None:
        with self._lock:
            self._policies.clear()
