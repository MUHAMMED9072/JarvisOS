from __future__ import annotations

from typing import Any

from app.core.logger import JarvisLogger


class PermissionDenied(Exception):
    """Raised when a plugin attempts an action without the required permission."""

    def __init__(
        self,
        plugin_name: str,
        permission: str,
        action: str = "",
    ) -> None:
        self.plugin_name = plugin_name
        self.permission = permission
        self.action = action
        msg = (
            f"Plugin {plugin_name!r} requires permission "
            f"{permission!r} for {action or 'this operation'}"
        )
        super().__init__(msg)


class Permission:
    """Built-in permission type constants."""

    AI = "ai"
    EVENTS = "events"
    SERVICES = "services"
    SKILLS = "skills"
    CONFIG = "config"
    MEMORY = "memory"
    FILESYSTEM = "filesystem"
    NETWORK = "network"

    _ALL = frozenset({
        AI, EVENTS, SERVICES, SKILLS, CONFIG,
        MEMORY, FILESYSTEM, NETWORK,
    })

    @classmethod
    def is_valid(cls, permission: str) -> bool:
        return permission in cls._ALL

    @classmethod
    def all_permissions(cls) -> list[str]:
        return sorted(cls._ALL)


class PermissionManager:
    """Manages and enforces permissions for a single plugin.

    If the plugin has not declared any permissions, all permissions
    are granted (backward compatible).  The effective set is computed
    once at construction time.
    """

    def __init__(
        self,
        plugin_name: str,
        permissions: list[str] | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._permissions: frozenset[str]

        if permissions:
            declared = {p for p in permissions if Permission.is_valid(p)}
            self._permissions = frozenset(declared)
        else:
            self._permissions = Permission._ALL

        JarvisLogger.info(
            "PermissionManager: plugin %r has permissions: %s",
            plugin_name, self.describe(),
        )

    @property
    def permissions(self) -> frozenset[str]:
        return self._permissions

    def check(self, permission: str, action: str = "") -> bool:
        """Check whether the plugin has *permission*.

        Returns True if granted, False if denied.
        """
        granted = permission in self._permissions
        if not granted:
            JarvisLogger.warning(
                "Permission denied for plugin %r: "
                "requires %r for %s (has: %s)",
                self._plugin_name, permission,
                action or "unknown",
                self.describe(),
            )
        return granted

    def require(self, permission: str, action: str = "") -> None:
        """Check permission and raise PermissionDenied if not granted."""
        if not self.check(permission, action):
            raise PermissionDenied(
                self._plugin_name, permission, action,
            )

    def has_all(self) -> bool:
        """Return True if the plugin has every built-in permission."""
        return self._permissions == Permission._ALL

    def describe(self) -> str:
        return ", ".join(sorted(self._permissions)) or "(none)"

    def to_list(self) -> list[str]:
        return sorted(self._permissions)
