# app/skills/system/info.py
from __future__ import annotations

from app.core.config import Config
from app.skills.base import Skill
from app.skills.result import SkillResult
from app.utils.system import (
    cpu_usage,
    ram_usage,
    disk_usage,
    current_time,
    python_version,
    operating_system,
    internet_status,
)


class SystemInfoSkill(Skill):
    name = "System Info"
    intent = "system_info"
    version = "1.0.0"
    description = "Returns system diagnostics including CPU, RAM, disk, OS, and network status."
    author = "JarvisOS"

    def run(self, request) -> SkillResult:
        data = {}
        errors = []

        # CPU Usage
        try:
            data["cpu_usage"] = cpu_usage()
        except Exception as e:
            data["cpu_usage"] = "unavailable"
            errors.append(f"cpu_usage: {e}")

        # RAM Usage
        try:
            data["ram_usage"] = ram_usage()
        except Exception as e:
            data["ram_usage"] = "unavailable"
            errors.append(f"ram_usage: {e}")

        # Disk Usage
        try:
            data["disk_usage"] = disk_usage()
        except Exception as e:
            data["disk_usage"] = "unavailable"
            errors.append(f"disk_usage: {e}")

        # Operating System
        try:
            data["os"] = operating_system()
        except Exception as e:
            data["os"] = "unavailable"
            errors.append(f"os: {e}")

        # Python Version
        try:
            data["python_version"] = python_version()
        except Exception as e:
            data["python_version"] = "unavailable"
            errors.append(f"python_version: {e}")

        # Internet Status
        try:
            data["internet"] = internet_status()
        except Exception as e:
            data["internet"] = "unavailable"
            errors.append(f"internet: {e}")

        # Current Time
        try:
            data["current_time"] = current_time()
        except Exception as e:
            data["current_time"] = "unavailable"
            errors.append(f"current_time: {e}")

        # JARVIS Version (from Config)
        try:
            data["jarvis_version"] = Config.VERSION
        except Exception as e:
            data["jarvis_version"] = "unavailable"
            errors.append(f"jarvis_version: {e}")

        # Skills Loaded (from injected skill_manager)
        try:
            if self.skill_manager is not None:
                data["skills_loaded"] = len(self.skill_manager.skills)
            else:
                data["skills_loaded"] = 0
                errors.append("skills_loaded: skill_manager not injected")
        except Exception as e:
            data["skills_loaded"] = 0
            errors.append(f"skills_loaded: {e}")

        data["errors"] = errors

        return SkillResult.ok(message="System info retrieved", data=data)