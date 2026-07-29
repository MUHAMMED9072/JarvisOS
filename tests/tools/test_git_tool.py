from __future__ import annotations

import os
import subprocess
import tempfile

import pytest

from app.tools.git_tool import GitTool


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


SKIP_GIT = pytest.mark.skipif(not _git_available(), reason="git not available on PATH")


class TestGitTool:
    def test_name_and_version(self) -> None:
        tool = GitTool()
        assert tool.name == "git_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = GitTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "repo_path" in names
        assert "message" in names

    def test_required_params(self) -> None:
        tool = GitTool()
        action_param = [p for p in tool.metadata.parameters if p.name == "action"][0]
        assert action_param.required is True

    def test_permissions(self) -> None:
        tool = GitTool()
        assert "tools.git.execute" in tool.metadata.permissions_required

    def test_validate_missing_action(self) -> None:
        tool = GitTool()
        errors = tool.validate_params({})
        assert any("action" in e for e in errors)

    def test_unknown_action(self) -> None:
        tool = GitTool()
        result = tool.execute({"action": "unknown_action_xyz"})
        assert not result.success
        assert "unknown" in (result.error_message or "").lower()

    @SKIP_GIT
    def test_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = GitTool()
            result = tool.execute({"action": "init", "repo_path": tmpdir})
            assert result.success
            assert os.path.exists(os.path.join(tmpdir, ".git"))

    @SKIP_GIT
    def test_status_initial(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = GitTool()
            tool.execute({"action": "init", "repo_path": tmpdir})
            result = tool.execute({"action": "status", "repo_path": tmpdir})
            assert result.success

    @SKIP_GIT
    def test_add_and_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = GitTool()
            tool.execute({"action": "init", "repo_path": tmpdir})
            test_file = os.path.join(tmpdir, "hello.txt")
            with open(test_file, "w") as f:
                f.write("hello")
            result = tool.execute({"action": "add", "repo_path": tmpdir, "paths": ["hello.txt"]})
            assert result.success
            result = tool.execute({"action": "commit", "repo_path": tmpdir, "message": "initial commit"})
            assert result.success

    @SKIP_GIT
    def test_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = GitTool()
            tool.execute({"action": "init", "repo_path": tmpdir})
            test_file = os.path.join(tmpdir, "f.txt")
            with open(test_file, "w") as f:
                f.write("data")
            tool.execute({"action": "add", "repo_path": tmpdir, "paths": ["f.txt"]})
            tool.execute({"action": "commit", "repo_path": tmpdir, "message": "first commit"})
            result = tool.execute({"action": "log", "repo_path": tmpdir, "args": "--oneline -5"})
            assert result.success
            assert len(result.output.get("log", [])) >= 1

    @SKIP_GIT
    def test_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = GitTool()
            tool.execute({"action": "init", "repo_path": tmpdir})
            test_file = os.path.join(tmpdir, "f.txt")
            with open(test_file, "w") as f:
                f.write("data")
            tool.execute({"action": "add", "repo_path": tmpdir, "paths": ["f.txt"]})
            tool.execute({"action": "commit", "repo_path": tmpdir, "message": "first"})
            result = tool.execute({"action": "branch", "repo_path": tmpdir, "branch": "feature"})
            assert result.success
            result = tool.execute({"action": "branch", "repo_path": tmpdir})
            assert result.success
            branches = result.output.get("branches", [])
            assert "feature" in branches

    @SKIP_GIT
    def test_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = GitTool()
            tool.execute({"action": "init", "repo_path": tmpdir})
            test_file = os.path.join(tmpdir, "f.txt")
            with open(test_file, "w") as f:
                f.write("data")
            tool.execute({"action": "add", "repo_path": tmpdir, "paths": ["f.txt"]})
            tool.execute({"action": "commit", "repo_path": tmpdir, "message": "first"})
            tool.execute({"action": "branch", "repo_path": tmpdir, "branch": "feature"})
            result = tool.execute({"action": "checkout", "repo_path": tmpdir, "branch": "feature"})
            assert result.success

    @SKIP_GIT
    def test_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = GitTool()
            tool.execute({"action": "init", "repo_path": tmpdir})
            test_file = os.path.join(tmpdir, "f.txt")
            with open(test_file, "w") as f:
                f.write("v1")
            tool.execute({"action": "add", "repo_path": tmpdir, "paths": ["f.txt"]})
            tool.execute({"action": "commit", "repo_path": tmpdir, "message": "first"})
            with open(test_file, "w") as f:
                f.write("v2")
            result = tool.execute({"action": "diff", "repo_path": tmpdir})
            assert result.success
            assert "v1" in (result.stdout or "")

    def test_commit_without_message(self) -> None:
        tool = GitTool()
        result = tool.execute({"action": "commit", "repo_path": "/tmp"})
        assert not result.success
        assert "message" in (result.error_message or "")

    def test_clone_without_url(self) -> None:
        tool = GitTool()
        result = tool.execute({"action": "clone", "repo_path": "/tmp"})
        assert not result.success
        assert "repo_url" in (result.error_message or "")

    def test_checkout_without_branch(self) -> None:
        tool = GitTool()
        result = tool.execute({"action": "checkout", "repo_path": "/tmp"})
        assert not result.success
        assert "branch" in (result.error_message or "")

    def test_merge_without_target(self) -> None:
        tool = GitTool()
        result = tool.execute({"action": "merge", "repo_path": "/tmp"})
        assert not result.success
        assert "target_branch" in (result.error_message or "")

    def test_to_dict(self) -> None:
        tool = GitTool()
        d = tool.to_dict()
        assert d["name"] == "git_tool"

    def test_capabilities(self) -> None:
        tool = GitTool()
        assert "git_operations" in tool.metadata.capabilities
