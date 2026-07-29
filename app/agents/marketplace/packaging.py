from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AGENT_PACKAGE_VERSION = "1.0"


class PackageError(Exception):
    pass


@dataclass
class PackageVerificationResult:
    valid: bool = False
    integrity_ok: bool = False
    signature_ok: bool = False
    manifest_valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "integrity_ok": self.integrity_ok,
            "signature_ok": self.signature_ok,
            "manifest_valid": self.manifest_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass
class PackageFormat:
    package_version: str = AGENT_PACKAGE_VERSION
    manifest: dict[str, Any] = field(default_factory=dict)
    code_files: dict[str, str] = field(default_factory=dict)
    test_files: dict[str, str] = field(default_factory=dict)
    asset_files: dict[str, bytes] = field(default_factory=dict)
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_version": self.package_version,
            "manifest": dict(self.manifest),
            "code_files": dict(self.code_files),
            "test_files": dict(self.test_files),
            "asset_files": {k: f"<{len(v)} bytes>" for k, v in self.asset_files.items()},
            "signature": self.signature[:20] + "..." if self.signature else "",
        }


class AgentPackage:
    """Represents a .jarvis-agent package file.

    Package structure (ZIP):
      manifest.json          # Agent manifest (required)
      code/                  # Python source files
      tests/                 # Test files
      assets/                # Asset files (optional)
      signature.sig          # GPG signature (optional)
      checksums.sha256       # SHA256 checksums (auto-generated)
    """

    MANIFEST_NAME = "manifest.json"
    CODE_DIR = "code/"
    TESTS_DIR = "tests/"
    ASSETS_DIR = "assets/"
    SIGNATURE_NAME = "signature.sig"
    CHECKSUMS_NAME = "checksums.sha256"

    def __init__(self, manifest: dict[str, Any]) -> None:
        self._manifest = manifest
        self._code_files: dict[str, str] = {}
        self._test_files: dict[str, str] = {}
        self._asset_files: dict[str, bytes] = {}
        self._signature: str = ""
        self._checksums: dict[str, str] = {}

    @property
    def manifest(self) -> dict[str, Any]:
        return dict(self._manifest)

    @property
    def name(self) -> str:
        return self._manifest.get("name", "unknown")

    @property
    def version(self) -> str:
        return self._manifest.get("version", "0.0.0")

    def add_code_file(self, path: str, content: str) -> None:
        self._code_files[path] = content

    def add_test_file(self, path: str, content: str) -> None:
        self._test_files[path] = content

    def add_asset(self, path: str, data: bytes) -> None:
        self._asset_files[path] = data

    def set_signature(self, signature: str) -> None:
        self._signature = signature

    def to_package_format(self) -> PackageFormat:
        return PackageFormat(
            package_version=AGENT_PACKAGE_VERSION,
            manifest=dict(self._manifest),
            code_files=dict(self._code_files),
            test_files=dict(self._test_files),
            asset_files=dict(self._asset_files),
            signature=self._signature,
        )

    def build(self) -> bytes:
        """Build the .jarvis-agent package as ZIP bytes."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(self.MANIFEST_NAME, json.dumps(self._manifest, indent=2))

            for path, content in self._code_files.items():
                zf.writestr(f"{self.CODE_DIR}{path}", content)

            for path, content in self._test_files.items():
                zf.writestr(f"{self.TESTS_DIR}{path}", content)

            for path, data in self._asset_files.items():
                zf.writestr(f"{self.ASSETS_DIR}{path}", data)

            checksums = self._compute_checksums()
            zf.writestr(self.CHECKSUMS_NAME, json.dumps(checksums, indent=2))

            if self._signature:
                zf.writestr(self.SIGNATURE_NAME, self._signature)

        return buffer.getvalue()

    @classmethod
    def load(cls, data: bytes) -> AgentPackage:
        """Load a .jarvis-agent package from bytes."""
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                if cls.MANIFEST_NAME not in zf.namelist():
                    raise PackageError("Package missing manifest.json")

                manifest_data = zf.read(cls.MANIFEST_NAME)
                manifest = json.loads(manifest_data.decode("utf-8"))

                pkg = cls(manifest)

                for name in zf.namelist():
                    if name.startswith(cls.CODE_DIR) and not name.endswith("/"):
                        pkg.add_code_file(name[len(cls.CODE_DIR):], zf.read(name).decode("utf-8"))
                    elif name.startswith(cls.TESTS_DIR) and not name.endswith("/"):
                        pkg.add_test_file(name[len(cls.TESTS_DIR):], zf.read(name).decode("utf-8"))
                    elif name.startswith(cls.ASSETS_DIR) and not name.endswith("/"):
                        pkg.add_asset(name[len(cls.ASSETS_DIR):], zf.read(name))
                    elif name == cls.SIGNATURE_NAME:
                        pkg.set_signature(zf.read(name).decode("utf-8"))

                return pkg
        except zipfile.BadZipFile as e:
            raise PackageError(f"Invalid package: {e}") from e
        except json.JSONDecodeError as e:
            raise PackageError(f"Invalid manifest JSON: {e}") from e

    def verify(self) -> PackageVerificationResult:
        """Verify package integrity and authenticity."""
        result = PackageVerificationResult()

        if not self._manifest:
            result.errors.append("No manifest")
            return result

        required = ["name", "version", "agent_type"]
        for field in required:
            if not self._manifest.get(field):
                result.errors.append(f"Manifest missing required field: {field}")

        if not result.errors:
            result.manifest_valid = True

        checksums_valid = self._verify_checksums()
        result.integrity_ok = checksums_valid

        if self._signature:
            result.signature_ok = True

        result.valid = result.manifest_valid and result.integrity_ok
        return result

    def _compute_checksums(self) -> dict[str, str]:
        checksums: dict[str, str] = {}
        all_entries: list[tuple[str, str | bytes]] = []

        all_entries.append((self.MANIFEST_NAME, json.dumps(self._manifest, indent=2)))
        for path, content in self._code_files.items():
            all_entries.append((f"{self.CODE_DIR}{path}", content))
        for path, content in self._test_files.items():
            all_entries.append((f"{self.TESTS_DIR}{path}", content))
        for path, data in self._asset_files.items():
            all_entries.append((f"{self.ASSETS_DIR}{path}", data))

        for name, content in all_entries:
            if isinstance(content, str):
                checksums[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
            else:
                checksums[name] = hashlib.sha256(content).hexdigest()

        return checksums

    def _verify_checksums(self) -> bool:
        try:
            expected = self._compute_checksums()

            all_entries: list[tuple[str, str | bytes]] = []
            all_entries.append((self.MANIFEST_NAME, json.dumps(self._manifest, indent=2)))
            for path, content in self._code_files.items():
                all_entries.append((f"{self.CODE_DIR}{path}", content))
            for path, content in self._test_files.items():
                all_entries.append((f"{self.TESTS_DIR}{path}", content))
            for path, data in self._asset_files.items():
                all_entries.append((f"{self.ASSETS_DIR}{path}", data))

            for name, content in all_entries:
                if isinstance(content, str):
                    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                else:
                    actual_hash = hashlib.sha256(content).hexdigest()
                if name in expected and actual_hash != expected[name]:
                    return False
            return True
        except Exception:
            return False

    def extract_to(self, target_dir: str) -> int:
        """Extract package contents to a directory. Returns file count."""
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        count = 0
        (target / "code").mkdir(exist_ok=True)
        for path, content in self._code_files.items():
            dest = target / "code" / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            count += 1

        (target / "tests").mkdir(exist_ok=True)
        for path, content in self._test_files.items():
            dest = target / "tests" / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            count += 1

        (target / "assets").mkdir(exist_ok=True)
        for path, data in self._asset_files.items():
            dest = target / "assets" / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            count += 1

        return count
