from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.memory.projects import ProjectMemory

_DATA_DIR = Path("data") / "memory"


@pytest.fixture
def pm():
    name = f"test_proj_{uuid.uuid4().hex}.json"
    p = ProjectMemory(filename=name)
    yield p
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()


class TestProjectMemory:
    def test_create_project_returns_id(self, pm):
        pid = pm.create_project("Test Project")
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_get_project(self, pm):
        pid = pm.create_project("My Project", description="desc")
        proj = pm.get_project(pid)
        assert proj is not None
        assert proj["name"] == "My Project"
        assert proj["description"] == "desc"

    def test_get_project_missing(self, pm):
        assert pm.get_project("nonexistent") is None

    def test_list_projects(self, pm):
        pm.create_project("A")
        pm.create_project("B")
        projects = pm.list_projects()
        assert len(projects) == 2

    def test_delete_project(self, pm):
        pid = pm.create_project("To Delete")
        assert pm.delete_project(pid) is True
        assert pm.get_project(pid) is None

    def test_delete_missing(self, pm):
        assert pm.delete_project("nonexistent") is False

    def test_update_project(self, pm):
        pid = pm.create_project("Old Name")
        updated = pm.update_project(pid, name="New Name", description="new desc")
        assert updated is not None
        assert updated["name"] == "New Name"
        assert updated["description"] == "new desc"

    def test_update_project_missing(self, pm):
        assert pm.update_project("nonexistent", name="x") is None

    def test_add_note(self, pm):
        pid = pm.create_project("Notes")
        assert pm.add_note(pid, "my note") is True
        proj = pm.get_project(pid)
        assert len(proj["notes"]) == 1
        assert proj["notes"][0]["content"] == "my note"

    def test_add_note_missing_project(self, pm):
        assert pm.add_note("nonexistent", "note") is False

    def test_add_file_ref(self, pm):
        pid = pm.create_project("Files")
        assert pm.add_file_ref(pid, "/path/to/file.txt") is True
        proj = pm.get_project(pid)
        assert len(proj["files"]) == 1

    def test_add_file_ref_missing_project(self, pm):
        assert pm.add_file_ref("nonexistent", "/path") is False

    def test_create_with_metadata(self, pm):
        pid = pm.create_project("Meta", metadata={"key": "val"})
        proj = pm.get_project(pid)
        assert proj["metadata"] == {"key": "val"}

    def test_clear(self, pm):
        pm.create_project("A")
        pm.create_project("B")
        pm.clear()
        assert pm.list_projects() == []

    def test_persistence(self, pm):
        pid = pm.create_project("Persist")
        pm2 = ProjectMemory(filename=pm.path.name)
        assert pm2.get_project(pid) is not None
