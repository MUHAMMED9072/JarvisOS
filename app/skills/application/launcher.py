import subprocess

from app.core.config import Config
from app.skills.base import Skill
from app.skills.result import SkillResult


class ApplicationLauncher(Skill):

    name = "Application Launcher"
    intent = "open_application"
    version = "1.0.0"
    description = "Launch installed Windows applications"

    def run(self, request):

        app = request.entities.get("application")

        if not app:
            return SkillResult.fail(
                "No application specified."
            )

        app = app.lower()

        applications = Config.APPLICATIONS

        if app not in applications:
            return SkillResult.fail(
                f"{app} is not supported."
            )

        subprocess.Popen(
            applications[app]
        )

        return SkillResult.ok(
            f"Opening {app}"
        )