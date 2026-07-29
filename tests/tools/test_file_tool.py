from __future__ import annotations

import os
import tempfile

import pytest

from app.tools.file_tool import FileTool


class TestFileTool:
    @pytest.fixture
    def tmp_base(self) -> str:
        with tempfile.TemporaryDirectory() as d:
            yield d

    def test_name_and_version(self) -> None:
        tool = FileTool()
        assert tool.name == "file_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = FileTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "path" in names
        assert "content" in names

    def test_permissions(self) -> None:
        tool = FileTool()
        assert "tools.file.access" in tool.metadata.permissions_required

    def test_validate_missing_action(self) -> None:
        tool = FileTool()
        errors = tool.validate_params({"path": "/tmp"})
        assert any("action" in e for e in errors)

    def test_read_file(self, tmp_base: str) -> None:
        filepath = os.path.join(tmp_base, "test.txt")
        with open(filepath, "w") as f:
            f.write("hello world")
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "read", "path": filepath})
        assert result.success
        assert result.output["content"] == "hello world"

    def test_read_nonexistent(self, tmp_base: str) -> None:
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "read", "path": os.path.join(tmp_base, "nonexistent.txt")})
        assert not result.success

    def test_write_file(self, tmp_base: str) -> None:
        filepath = os.path.join(tmp_base, "written.txt")
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "write", "path": filepath, "content": "test content"})
        assert result.success
        with open(filepath) as f:
            assert f.read() == "test content"

    def test_write_creates_dirs(self, tmp_base: str) -> None:
        filepath = os.path.join(tmp_base, "a", "b", "nested.txt")
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "write", "path": filepath, "content": "nested"})
        assert result.success
        assert os.path.exists(filepath)

    def test_copy_file(self, tmp_base: str) -> None:
        src = os.path.join(tmp_base, "src.txt")
        dst = os.path.join(tmp_base, "dst.txt")
        with open(src, "w") as f:
            f.write("copy me")
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "copy", "path": src, "destination": dst})
        assert result.success
        with open(dst) as f:
            assert f.read() == "copy me"

    def test_move_file(self, tmp_base: str) -> None:
        src = os.path.join(tmp_base, "move_src.txt")
        dst = os.path.join(tmp_base, "move_dst.txt")
        with open(src, "w") as f:
            f.write("move me")
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "move", "path": src, "destination": dst})
        assert result.success
        assert os.path.exists(dst)
        assert not os.path.exists(src)

    def test_delete_file(self, tmp_base: str) -> None:
        filepath = os.path.join(tmp_base, "delete_me.txt")
        with open(filepath, "w") as f:
            f.write("delete me")
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "delete", "path": filepath})
        assert result.success
        assert not os.path.exists(filepath)

    def test_list_directory(self, tmp_base: str) -> None:
        for name in ["a.txt", "b.txt", "sub"]:
            p = os.path.join(tmp_base, name)
            if name == "sub":
                os.makedirs(p)
            else:
                with open(p, "w") as f:
                    f.write(name)
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "list", "path": tmp_base})
        assert result.success
        names = [e["name"] for e in result.output["entries"]]
        assert "a.txt" in names
        assert "b.txt" in names
        assert "sub" in names

    def test_path_traversal_blocked(self, tmp_base: str) -> None:
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "read", "path": os.path.join(tmp_base, "..", "..", "etc", "passwd")})
        assert not result.success
        assert "traversal" in (result.error_message or "").lower()

    def test_unknown_action(self, tmp_base: str) -> None:
        tool = FileTool(allowed_base=tmp_base)
        result = tool.execute({"action": "unknown", "path": tmp_base})
        assert not result.success
        assert "unknown" in (result.error_message or "")

    def test_to_dict(self) -> None:
        tool = FileTool()
        d = tool.to_dict()
        assert d["name"] == "file_tool"

    def test_capabilities(self) -> None:
        tool = FileTool()
        assert "file_operations" in tool.metadata.capabilities
