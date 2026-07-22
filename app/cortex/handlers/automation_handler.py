from __future__ import annotations

import subprocess

from app.core.config import Config
from app.cortex.handlers import BaseHandler


class AutomationHandler(BaseHandler):
    """Thin wrapper around OS automation utilities."""

    def open_application(self, name: str) -> str:
        applications = Config.APPLICATIONS
        app = name.lower()
        if app not in applications:
            return f"{name} is not a supported application."
        subprocess.Popen(applications[app])
        return f"Opening {app}"

    def close_application(self, name: str) -> str:
        try:
            subprocess.run(
                ["taskkill", "/IM", f"{name}.exe", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return f"Closing {name}"
        except Exception:
            return f"Could not close {name}"

    def search_web(self, query: str) -> str:
        return f"Searching for: {query}"
