"""Tests for the Evolution Engine's RollbackManager.

Covers the file/directory backup + restore path that P3-24 wired in
so the Installer can use it to roll back a failed install against
a single-file target.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evolution.rollback import RollbackManager


class TestRollbackManagerFileBackup:
    """Backup and restore a single file."""

    def test_create_backup_writes_marker_and_copies_file(self, tmp_path: Path) -> None:
        source = tmp_path / "loader.py"
        source.write_text("original\n", encoding="utf-8")
        backup_dir = tmp_path / "backups" / "loader.py-20240101"

        result = RollbackManager().create_backup(str(source), str(backup_dir))

        assert result.success is True
        assert backup_dir.is_dir()
        assert (backup_dir / "loader.py").read_text(encoding="utf-8") == "original\n"
        marker = json.loads(
            (backup_dir / RollbackManager.MARKER).read_text(encoding="utf-8")
        )
        assert marker == {"source_type": "file", "source_name": "loader.py"}

    def test_round_trip_file_backup_restores_content(self, tmp_path: Path) -> None:
        source = tmp_path / "subdir" / "loader.py"
        source.parent.mkdir(parents=True)
        source.write_text("version-1\n", encoding="utf-8")
        backup_dir = tmp_path / "backups" / "loader.py-snap"

        RollbackManager().create_backup(str(source), str(backup_dir))

        # Simulate the patch replacing the file
        source.write_text("version-2\n", encoding="utf-8")

        result = RollbackManager().restore(str(backup_dir), str(source))

        assert result.success is True
        assert source.read_text(encoding="utf-8") == "version-1\n"

    def test_create_backup_overwrites_existing_backup_dir(self, tmp_path: Path) -> None:
        source = tmp_path / "loader.py"
        source.write_text("v1\n", encoding="utf-8")
        backup_dir = tmp_path / "backups" / "snap"
        backup_dir.mkdir(parents=True)
        (backup_dir / "stale.txt").write_text("stale", encoding="utf-8")

        result = RollbackManager().create_backup(str(source), str(backup_dir))

        assert result.success is True
        assert not (backup_dir / "stale.txt").exists()
        assert (backup_dir / "loader.py").read_text(encoding="utf-8") == "v1\n"

    def test_create_backup_missing_source_returns_failure(
        self, tmp_path: Path,
    ) -> None:
        missing = tmp_path / "does_not_exist.py"
        backup_dir = tmp_path / "backups" / "snap"

        result = RollbackManager().create_backup(str(missing), str(backup_dir))

        assert result.success is False
        assert "not found" in result.message.lower()


class TestRollbackManagerDirectoryBackup:
    """Backup and restore a directory."""

    def test_create_backup_writes_marker_for_directory(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "pkg"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("a", encoding="utf-8")
        (src_dir / "b.py").write_text("b", encoding="utf-8")
        backup_dir = tmp_path / "backups" / "pkg-snap"

        result = RollbackManager().create_backup(str(src_dir), str(backup_dir))

        assert result.success is True
        marker = json.loads(
            (backup_dir / RollbackManager.MARKER).read_text(encoding="utf-8")
        )
        assert marker == {"source_type": "directory", "source_name": "pkg"}
        assert (backup_dir / "pkg" / "a.py").read_text(encoding="utf-8") == "a"

    def test_round_trip_directory_backup_restores_tree(
        self, tmp_path: Path,
    ) -> None:
        src_dir = tmp_path / "pkg"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("a", encoding="utf-8")
        backup_dir = tmp_path / "backups" / "pkg-snap"

        RollbackManager().create_backup(str(src_dir), str(backup_dir))

        # Mutate the source
        (src_dir / "a.py").write_text("mutated", encoding="utf-8")
        (src_dir / "new.py").write_text("new", encoding="utf-8")

        result = RollbackManager().restore(str(backup_dir), str(src_dir))

        assert result.success is True
        assert (src_dir / "a.py").read_text(encoding="utf-8") == "a"
        assert not (src_dir / "new.py").exists()


class TestRollbackManagerRestoreErrors:
    """Failure paths in restore()."""

    def test_restore_missing_backup_dir_returns_failure(
        self, tmp_path: Path,
    ) -> None:
        result = RollbackManager().restore(
            str(tmp_path / "no-such-dir"),
            str(tmp_path / "dest.py"),
        )

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_restore_missing_marker_returns_failure(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups" / "snap"
        backup_dir.mkdir(parents=True)
        # No .rollback.json marker present

        result = RollbackManager().restore(
            str(backup_dir), str(tmp_path / "dest.py"),
        )

        assert result.success is False
        assert "marker" in result.message.lower()

    def test_restore_missing_backup_item_returns_failure(
        self, tmp_path: Path,
    ) -> None:
        backup_dir = tmp_path / "backups" / "snap"
        backup_dir.mkdir(parents=True)
        # Marker claims a file called "loader.py" but the file is absent
        (backup_dir / RollbackManager.MARKER).write_text(
            json.dumps({"source_type": "file", "source_name": "loader.py"}),
            encoding="utf-8",
        )

        result = RollbackManager().restore(
            str(backup_dir), str(tmp_path / "loader.py"),
        )

        assert result.success is False
        assert "not found" in result.message.lower()
