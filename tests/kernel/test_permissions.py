"""Tests for the kernel security permission system."""

from __future__ import annotations

import threading

import pytest

from app.kernel.security.permissions import (
    ALL_PERMISSIONS,
    HIERARCHY,
    ROOT_GROUPS,
    KernelPermission,
    PermissionGroup,
    PermissionRegistry,
    get_permission_registry,
)


class TestKernelPermission:
    def test_flat_permissions_compatible_with_plugin_sdk(self):
        assert KernelPermission.AI == "ai"
        assert KernelPermission.EVENTS == "events"
        assert KernelPermission.SERVICES == "services"
        assert KernelPermission.SKILLS == "skills"
        assert KernelPermission.CONFIG == "config"
        assert KernelPermission.MEMORY == "memory"
        assert KernelPermission.FILESYSTEM == "filesystem"
        assert KernelPermission.NETWORK == "network"

    def test_is_valid_accepts_flat_permissions(self):
        assert KernelPermission.is_valid("ai") is True
        assert KernelPermission.is_valid("events") is True

    def test_is_valid_accepts_hierarchical_permissions(self):
        assert KernelPermission.is_valid("ai.ask") is True
        assert KernelPermission.is_valid("filesystem.read") is True
        assert KernelPermission.is_valid("system.shutdown") is True

    def test_is_valid_rejects_unknown_permissions(self):
        assert KernelPermission.is_valid("nonexistent") is False
        assert KernelPermission.is_valid("ai.nonexistent") is False

    def test_all_permissions_includes_both_flat_and_hierarchical(self):
        perms = KernelPermission.all_permissions()
        assert "ai" in perms
        assert "ai.ask" in perms
        assert "filesystem.read" in perms

    def test_all_permissions_no_duplicates(self):
        perms = KernelPermission.all_permissions()
        assert len(perms) == len(set(perms))


class TestPermissionGroup:
    def test_create_group(self):
        g = PermissionGroup("test")
        assert g.name == "test"
        assert g.parent is None

    def test_create_group_with_parent(self):
        parent = PermissionGroup("parent")
        child = PermissionGroup("child", parent=parent)
        assert child.parent is parent

    def test_add_child(self):
        parent = PermissionGroup("parent")
        child = PermissionGroup("child")
        parent.add_child(child)
        assert "child" in parent.children

    def test_add_permission(self):
        g = PermissionGroup("test")
        g.add_permission("test.read")
        assert "test.read" in g.permissions

    def test_flatten_includes_own_permissions(self):
        g = PermissionGroup("root")
        g.add_permission("root.read")
        flat = g.flatten()
        assert "root.read" in flat

    def test_flatten_includes_child_permissions(self):
        root = PermissionGroup("root")
        child = PermissionGroup("child")
        child.add_permission("child.read")
        root.add_child(child)
        flat = root.flatten()
        assert "child.read" in flat

    def test_repr(self):
        g = PermissionGroup("test")
        assert repr(g) == "PermissionGroup('test')"


class TestPermissionRegistry:
    @pytest.fixture
    def registry(self):
        return PermissionRegistry()

    def test_register_group(self, registry):
        g = registry.register_group("test-group")
        assert g.name == "test-group"
        assert registry.get_group("test-group") is g

    def test_register_group_with_parent(self, registry):
        parent = registry.register_group("parent")
        child = registry.register_group("child", parent=parent)
        assert child.parent is parent

    def test_get_group_nonexistent(self, registry):
        assert registry.get_group("nonexistent") is None

    def test_list_groups(self, registry):
        registry.register_group("a")
        registry.register_group("b")
        groups = registry.list_groups()
        assert "a" in groups
        assert "b" in groups

    def test_list_groups_sorted(self, registry):
        registry.register_group("z")
        registry.register_group("a")
        assert registry.list_groups() == ["a", "z"]

    def test_is_valid_known(self, registry):
        assert registry.is_valid("ai.ask") is True

    def test_is_valid_unknown(self, registry):
        assert registry.is_valid("foo.bar") is False

    def test_has_permission_exact_match(self, registry):
        assert registry.has_permission("ai.ask", {"ai.ask"}) is True

    def test_has_permission_wildcard(self, registry):
        assert registry.has_permission("ai.ask", {"*"}) is True

    def test_has_permission_group_wildcard(self, registry):
        assert registry.has_permission("ai.ask", {"ai.*"}) is True

    def test_has_permission_denied(self, registry):
        assert registry.has_permission("ai.ask", {"memory.read"}) is False

    def test_has_permission_empty_set(self, registry):
        assert registry.has_permission("ai.ask", set()) is False

    def test_check_delegates(self, registry):
        assert registry.check("ai.ask", {"ai.ask"}) is True
        assert registry.check("ai.ask", set()) is False

    def test_require_passes(self, registry):
        registry.require("ai.ask", {"ai.ask"}, actor="test")

    def test_require_raises(self, registry):
        with pytest.raises(PermissionError):
            registry.require("ai.ask", set(), actor="test")

    def test_describe(self, registry):
        desc = registry.describe({"ai.ask", "memory.read"})
        assert "ai.ask" in desc
        assert "memory.read" in desc

    def test_describe_empty(self, registry):
        assert registry.describe(set()) == "(none)"

    def test_thread_safe_concurrent_register(self, registry):
        def register_group(i):
            registry.register_group(f"thread-{i}")

        threads = [threading.Thread(target=register_group, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for i in range(20):
            assert registry.get_group(f"thread-{i}") is not None


class TestPermissionRegistrySingleton:
    def test_get_permission_registry_returns_singleton(self):
        r1 = get_permission_registry()
        r2 = get_permission_registry()
        assert r1 is r2

    def test_singleton_has_root_groups(self):
        reg = get_permission_registry()
        for group in ROOT_GROUPS:
            assert reg.get_group(group) is not None, f"Missing group: {group}"


class TestHierarchy:
    def test_all_known_groups_in_hierarchy(self):
        for group in ROOT_GROUPS:
            assert group in HIERARCHY, f"Missing hierarchy entry for {group}"

    def test_all_permissions_contains_hierarchy(self):
        for perms in HIERARCHY.values():
            for p in perms:
                assert p in ALL_PERMISSIONS, f"Missing permission: {p}"

    def test_hierarchical_permission_format(self):
        for group, perms in HIERARCHY.items():
            for p in perms:
                assert p.startswith(f"{group}."), (
                    f"Permission {p!r} should start with {group!r}."
                )

    def test_non_empty_hierarchy(self):
        for group, perms in HIERARCHY.items():
            assert len(perms) > 0, f"Group {group} has no permissions"

    def test_no_duplicate_permissions_in_hierarchy(self):
        all_perms = []
        for perms in HIERARCHY.values():
            all_perms.extend(perms)
        assert len(all_perms) == len(set(all_perms))
