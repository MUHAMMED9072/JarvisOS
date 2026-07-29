from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


# Known dangerous permission combinations
_DANGEROUS_PERM_COMBOS: list[list[str]] = [
    ["file:write", "file:execute"],
    ["network:all", "file:read_all"],
    ["shell:execute", "network:all"],
    ["file:write_system", "process:spawn"],
    ["network:listen", "shell:execute"],
]

_SENSITIVE_FILES: list[str] = [
    "/etc/passwd", "/etc/shadow", "/etc/ssh/", "~/.ssh/",
    "/var/log/", "/var/db/", "/etc/kubernetes/",
    "config.json", ".env", "credentials",
    "id_rsa", "id_ed25519", "known_hosts",
]

_KNOWN_VULNERABILITIES: dict[str, list[str]] = {
    "requests<2.28.0": ["CVE-2023-32681", "CRLF injection"],
    "urllib3<1.26.18": ["CVE-2023-45803", "Request body injection"],
    "cryptography<41.0.0": ["CVE-2023-23931", "Bleichenbacher oracle"],
    "flask<2.3.0": ["CVE-2023-30861", "Information disclosure"],
    "django<4.2.0": ["CVE-2023-31047", "Directory traversal"],
    "pillow<10.0.0": ["CVE-2023-44271", "Memory corruption"],
    "pyyaml<6.0": ["CVE-2020-14343", "Arbitrary code execution"],
    "numpy<1.22.0": ["CVE-2021-41496", "Buffer overflow"],
    "werkzeug<2.3.0": ["CVE-2023-46136", "Denial of service"],
}


@dataclass
class PermissionAnalysis:
    requested_permissions: list[str] = field(default_factory=list)
    excessive_permissions: list[str] = field(default_factory=list)
    dangerous_combinations: list[list[str]] = field(default_factory=list)
    justified: bool = True
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_permissions": list(self.requested_permissions),
            "excessive_permissions": list(self.excessive_permissions),
            "dangerous_combinations": [list(c) for c in self.dangerous_combinations],
            "justified": self.justified,
            "score": self.score,
        }


@dataclass
class ExternalConnectionAnalysis:
    domains: list[str] = field(default_factory=list)
    ip_addresses: list[str] = field(default_factory=list)
    unencrypted: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": list(self.domains),
            "ip_addresses": list(self.ip_addresses),
            "unencrypted": list(self.unencrypted),
            "score": self.score,
        }


@dataclass
class FileAccessAnalysis:
    files_accessed: list[str] = field(default_factory=list)
    sensitive_files: list[str] = field(default_factory=list)
    write_access: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_accessed": list(self.files_accessed),
            "sensitive_files": list(self.sensitive_files),
            "write_access": list(self.write_access),
            "score": self.score,
        }


@dataclass
class DependencyVulnerability:
    dependency: str = ""
    cve: str = ""
    description: str = ""
    severity: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependency": self.dependency,
            "cve": self.cve,
            "description": self.description,
            "severity": self.severity,
        }


@dataclass
class DependencyVulnerabilityCheck:
    vulnerabilities: list[DependencyVulnerability] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
            "score": self.score,
        }


@dataclass
class SecurityImpactReport:
    artifact_name: str = ""
    artifact_type: str = ""
    permission_analysis: PermissionAnalysis = field(default_factory=PermissionAnalysis)
    external_connections: ExternalConnectionAnalysis = field(default_factory=ExternalConnectionAnalysis)
    file_access: FileAccessAnalysis = field(default_factory=FileAccessAnalysis)
    dependency_vulnerabilities: DependencyVulnerabilityCheck = field(default_factory=DependencyVulnerabilityCheck)
    overall_score: float = 0.0
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "permission_analysis": self.permission_analysis.to_dict(),
            "external_connections": self.external_connections.to_dict(),
            "file_access": self.file_access.to_dict(),
            "dependency_vulnerabilities": self.dependency_vulnerabilities.to_dict(),
            "overall_score": self.overall_score,
            "passed": self.passed,
        }


_URL_PATTERN = re.compile(r'https?://([^\s/\"\']+)')
_IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
_FILE_PATTERN = re.compile(r'[\"\'](/[^\s\"\']+)[\"\']')
_URLOPEN_PATTERN = re.compile(r'urlopen\([\"\' ]*(https?://[^\"\')]+)')


class SecurityAnalyzer:
    """Analyze security impact of artifacts.

    Evaluates attack surface, permissions, external connections,
    file system access, and dependency vulnerabilities.

    Thread-safe.
    """

    def __init__(self, graph_store: GraphStore | None = None) -> None:
        self._graph = graph_store
        self._lock = threading.RLock()
        self._vulnerability_db: dict[str, list[str]] = dict(_KNOWN_VULNERABILITIES)

    def analyze(
        self,
        source_code: str,
        artifact_name: str = "",
        artifact_type: str = "agent",
        permissions: list[str] | None = None,
        dependencies: list[str] | None = None,
    ) -> SecurityImpactReport:
        permission_analysis = self._analyze_permissions(permissions or [])
        ext_connections = self._analyze_external_connections(source_code)
        file_access = self._analyze_file_access(source_code)
        dep_vulns = self._check_dependency_vulnerabilities(dependencies or [])

        overall_score = self._compute_overall_score(
            permission_analysis.score,
            ext_connections.score,
            file_access.score,
            dep_vulns.score,
        )

        return SecurityImpactReport(
            artifact_name=artifact_name,
            artifact_type=artifact_type,
            permission_analysis=permission_analysis,
            external_connections=ext_connections,
            file_access=file_access,
            dependency_vulnerabilities=dep_vulns,
            overall_score=overall_score,
            passed=overall_score < 0.7,
        )

    def _analyze_permissions(self, permissions: list[str]) -> PermissionAnalysis:
        requested = list(permissions)
        excessive: list[str] = []
        dangerous_combos: list[list[str]] = []

        high_risk_perms = {"shell:execute", "network:listen", "file:write_system", "process:spawn"}
        for p in requested:
            if p in high_risk_perms:
                excessive.append(p)

        for combo in _DANGEROUS_PERM_COMBOS:
            if all(p in requested for p in combo):
                dangerous_combos.append(combo)

        score = 0.0
        if requested:
            score += len(excessive) * 0.15
            score += len(dangerous_combos) * 0.2
            if len(requested) > 5:
                score += 0.1
        score = min(1.0, score)

        return PermissionAnalysis(
            requested_permissions=requested,
            excessive_permissions=excessive,
            dangerous_combinations=dangerous_combos,
            justified=len(excessive) == 0 and len(dangerous_combos) == 0,
            score=score,
        )

    def _analyze_external_connections(self, source: str) -> ExternalConnectionAnalysis:
        domains: list[str] = []
        ip_addresses: list[str] = []
        unencrypted: list[str] = []

        for m in _URL_PATTERN.finditer(source):
            domain = m.group(1)
            full_url = m.group(0)
            if domain not in domains:
                domains.append(domain)
            if full_url.startswith("http://"):
                if domain not in unencrypted:
                    unencrypted.append(domain)

        for m in _IP_PATTERN.finditer(source):
            ip = m.group(0)
            if ip not in ip_addresses:
                ip_addresses.append(ip)

        score = 0.0
        if domains:
            score += min(len(domains) * 0.1, 0.4)
        if unencrypted:
            score += min(len(unencrypted) * 0.15, 0.3)
        if ip_addresses:
            score += min(len(ip_addresses) * 0.05, 0.2)

        return ExternalConnectionAnalysis(
            domains=domains,
            ip_addresses=ip_addresses,
            unencrypted=unencrypted,
            score=min(1.0, score),
        )

    def _analyze_file_access(self, source: str) -> FileAccessAnalysis:
        files_accessed: list[str] = []
        sensitive: list[str] = []
        write_access: list[str] = []

        for m in _FILE_PATTERN.finditer(source):
            fpath = m.group(1)
            if fpath not in files_accessed:
                files_accessed.append(fpath)
            if any(s in fpath for s in _SENSITIVE_FILES):
                sensitive.append(fpath)

        if ".write(" in source or "open(" in source:
            for m in _FILE_PATTERN.finditer(source):
                fp = m.group(1)
                if fp not in write_access:
                    write_access.append(fp)

        score = 0.0
        if sensitive:
            score += min(len(sensitive) * 0.2, 0.6)
        if len(files_accessed) > 10:
            score += 0.1
        if write_access:
            score += min(len(write_access) * 0.05, 0.2)

        return FileAccessAnalysis(
            files_accessed=files_accessed,
            sensitive_files=sensitive,
            write_access=write_access,
            score=min(1.0, score),
        )

    def _check_dependency_vulnerabilities(
        self, dependencies: list[str],
    ) -> DependencyVulnerabilityCheck:
        vulns: list[DependencyVulnerability] = []

        for dep in dependencies:
            dep_lower = dep.lower().strip()
            # Check exact match
            for known_dep, cve_info in self._vulnerability_db.items():
                known_name = known_dep.split("<")[0].strip().lower()
                if known_name == dep_lower or dep_lower.startswith(known_name):
                    vulns.append(DependencyVulnerability(
                        dependency=dep,
                        cve=cve_info[0],
                        description=cve_info[1] if len(cve_info) > 1 else "Known vulnerability",
                        severity="medium",
                    ))
                    break

        score = min(len(vulns) * 0.2, 1.0)
        return DependencyVulnerabilityCheck(vulnerabilities=vulns, score=score)

    def _compute_overall_score(
        self,
        perm_score: float,
        conn_score: float,
        file_score: float,
        dep_score: float,
    ) -> float:
        return min(1.0, perm_score * 0.3 + conn_score * 0.25 + file_score * 0.25 + dep_score * 0.2)

    def add_vulnerability(self, dependency_pattern: str, cve: str, description: str) -> None:
        with self._lock:
            self._vulnerability_db[dependency_pattern] = [cve, description]

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "vulnerability_count": len(self._vulnerability_db),
        }
