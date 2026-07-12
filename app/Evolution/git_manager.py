"""
JARVIS Evolution Engine - Git Manager
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class GitResult:
    success: bool
    output: str
    error: str


class GitManager:
    def _run(self, *args: str) -> GitResult:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
        )
        return GitResult(
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
        )

    def status(self) -> GitResult:
        return self._run("status", "--short")

    def add_all(self) -> GitResult:
        return self._run("add", ".")

    def commit(self, message: str) -> GitResult:
        return self._run("commit", "-m", message)

    def current_branch(self) -> GitResult:
        return self._run("branch", "--show-current")


if __name__ == "__main__":
    git = GitManager()
    print(git.current_branch())
