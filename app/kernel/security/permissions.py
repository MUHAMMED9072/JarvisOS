from __future__ import annotations

import threading
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Built-in permission names (flat — backward compatible with Plugin SDK)
# ---------------------------------------------------------------------------

AI = "ai"
EVENTS = "events"
SERVICES = "services"
SKILLS = "skills"
CONFIG = "config"
MEMORY = "memory"
FILESYSTEM = "filesystem"
NETWORK = "network"

_FLAT_PERMISSIONS: frozenset[str] = frozenset({
    AI, EVENTS, SERVICES, SKILLS, CONFIG, MEMORY, FILESYSTEM, NETWORK,
})

# ---------------------------------------------------------------------------
# Hierarchical permission groups
# ---------------------------------------------------------------------------
# Each group is a parent node in the permission tree.  Every permission
# string is either a group name (e.g. "ai") or a dot-separated path
# rooted at a group (e.g. "ai.read", "filesystem.write").

GROUP_SYSTEM = "system"
GROUP_ADMIN = "admin"
GROUP_AI = AI
GROUP_EVENTS = EVENTS
GROUP_SERVICES = SERVICES
GROUP_SKILLS = SKILLS
GROUP_CONFIG = CONFIG
GROUP_MEMORY = MEMORY
GROUP_FILESYSTEM = FILESYSTEM
GROUP_NETWORK = NETWORK
GROUP_PLUGIN = "plugin"

GROUP_AUDIT = "audit"

ROOT_GROUPS: tuple[str, ...] = (
    GROUP_SYSTEM,
    GROUP_ADMIN,
    GROUP_AI,
    GROUP_EVENTS,
    GROUP_SERVICES,
    GROUP_SKILLS,
    GROUP_CONFIG,
    GROUP_MEMORY,
    GROUP_FILESYSTEM,
    GROUP_NETWORK,
    GROUP_PLUGIN,
    GROUP_AUDIT,
)

HIERARCHY: dict[str, tuple[str, ...]] = {
    GROUP_SYSTEM: (
        "system.shutdown",
        "system.restart",
        "system.maintenance",
        "system.evolution",
        "system.health.read",
        "system.audit.read",
    ),
    GROUP_ADMIN: (
        "admin.agents.manage",
        "admin.agents.pause",
        "admin.agents.resume",
        "admin.agents.retire",
        "admin.users.manage",
        "admin.policies.manage",
        "admin.scheduler.manage",
    ),
    GROUP_AI: (
        "ai.ask",
        "ai.ask_stream",
        "ai.plan",
        "ai.reason",
        "ai.conversation.create",
        "ai.conversation.read",
        "ai.conversation.delete",
        "ai.structured.create",
        "ai.structured.parse",
        "ai.tools.register",
        "ai.tools.unregister",
        "ai.templates.register",
        "ai.templates.unregister",
    ),
    GROUP_EVENTS: (
        "events.subscribe",
        "events.publish",
        "events.unsubscribe",
    ),
    GROUP_SERVICES: (
        "services.register",
        "services.get",
        "services.list",
    ),
    GROUP_SKILLS: (
        "skills.register",
        "skills.unregister",
        "skills.execute",
    ),
    GROUP_CONFIG: (
        "config.read",
        "config.write",
        "config.reload",
    ),
    GROUP_MEMORY: (
        "memory.store",
        "memory.read",
        "memory.delete",
        "memory.search",
    ),
    GROUP_FILESYSTEM: (
        "filesystem.read",
        "filesystem.write",
        "filesystem.delete",
        "filesystem.execute",
    ),
    GROUP_NETWORK: (
        "network.connect",
        "network.http",
        "network.websocket",
    ),
    GROUP_PLUGIN: (
        "plugin.install",
        "plugin.uninstall",
        "plugin.enable",
        "plugin.disable",
        "plugin.configure",
    ),
    GROUP_AUDIT: (
        "audit.read",
        "audit.write",
    ),
}

ALL_PERMISSIONS: frozenset[str] = frozenset(
    _FLAT_PERMISSIONS
    | {p for perms in HIERARCHY.values() for p in perms}
    | set(ROOT_GROUPS)
)


class PermissionGroup:
    """A named group of permissions in the hierarchy."""

    def __init__(
        self,
        name: str,
        parent: Optional[PermissionGroup] = None,
        description: str = "",
    ) -> None:
        self.name = name
        self.parent = parent
        self.description = description
        self._children: dict[str, PermissionGroup] = {}
        self._permissions: set[str] = set()

    def add_child(self, group: PermissionGroup) -> None:
        self._children[group.name] = group

    def add_permission(self, permission: str) -> None:
        self._permissions.add(permission)

    @property
    def children(self) -> dict[str, PermissionGroup]:
        return dict(self._children)

    @property
    def permissions(self) -> frozenset[str]:
        return frozenset(self._permissions)

    def flatten(self) -> set[str]:
        result: set[str] = set(self._permissions)
        for child in self._children.values():
            result.update(child.flatten())
        return result

    def __repr__(self) -> str:
        return f"PermissionGroup({self.name!r})"


class PermissionRegistry:
    """Thread-safe registry of all kernel permission definitions.

    Provides:
    - Registration and lookup of permissions
    - Hierarchical grouping
    - Validation (is a permission known?)
    - ``check()`` and ``require()`` against a set of granted permissions
    - Deny-by-default: any permission not explicitly granted is denied.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._groups: dict[str, PermissionGroup] = {}

    def register_group(
        self,
        name: str,
        parent: Optional[PermissionGroup] = None,
        description: str = "",
    ) -> PermissionGroup:
        with self._lock:
            group = PermissionGroup(name, parent=parent, description=description)
            self._groups[name] = group
            return group

    def get_group(self, name: str) -> Optional[PermissionGroup]:
        with self._lock:
            return self._groups.get(name)

    def list_groups(self) -> list[str]:
        with self._lock:
            return sorted(self._groups.keys())

    def is_valid(self, permission: str) -> bool:
        return permission in ALL_PERMISSIONS

    def all_permissions(self) -> list[str]:
        return sorted(ALL_PERMISSIONS)

    def has_permission(
        self,
        permission: str,
        granted: set[str] | frozenset[str],
    ) -> bool:
        if permission in granted:
            return True
        if "*" in granted:
            return True
        for g in granted:
            if g.endswith(".*") and permission.startswith(g[:-1]):
                return True
        return False

    def check(
        self,
        permission: str,
        granted: set[str] | frozenset[str],
    ) -> bool:
        return self.has_permission(permission, granted)

    def require(
        self,
        permission: str,
        granted: set[str] | frozenset[str],
        actor: str = "",
    ) -> None:
        if not self.check(permission, granted):
            raise PermissionError(
                f"{actor} requires permission {permission!r}".strip()
            )

    def describe(self, granted: set[str] | frozenset[str]) -> str:
        return ", ".join(sorted(granted)) if granted else "(none)"


# Singleton
_registry: Optional[PermissionRegistry] = None
_registry_lock = threading.Lock()


def get_permission_registry() -> PermissionRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = PermissionRegistry()
                for group_name in ROOT_GROUPS:
                    _registry.register_group(group_name, description=f"Permission group: {group_name}")
    return _registry


class KernelPermission:
    """Kernel-level permission constants (mirrors Plugin SDK ``Permission``).

    All values are also valid in the hierarchical system for backward
    compatibility.  New code should prefer the dotted ``"group.action"`` form.
    """

    AI = AI
    EVENTS = EVENTS
    SERVICES = SERVICES
    SKILLS = SKILLS
    CONFIG = CONFIG
    MEMORY = MEMORY
    FILESYSTEM = FILESYSTEM
    NETWORK = NETWORK

    _ALL = _FLAT_PERMISSIONS

    @classmethod
    def is_valid(cls, permission: str) -> bool:
        return permission in ALL_PERMISSIONS

    @classmethod
    def all_permissions(cls) -> list[str]:
        return sorted(ALL_PERMISSIONS)
