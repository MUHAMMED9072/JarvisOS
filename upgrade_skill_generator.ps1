# ==========================================
# JARVIS Skill Generator Installer
# ==========================================

function Write-PyFile($Path, $Content) {
    $Dir = Split-Path $Path
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    Set-Content -Path $Path -Value $Content -Encoding UTF8
    Write-Host "Installed $Path" -ForegroundColor Green
}

New-Item -ItemType Directory -Force -Path "app\generator" | Out-Null
New-Item -ItemType Directory -Force -Path "app\skills\generated" | Out-Null

Write-PyFile "app\generator\__init__.py" ""

Write-PyFile "app\generator\templates.py" @'
SKILL_TEMPLATE = """
class {class_name}:
    name = "{skill_name}"

    def run(self, **kwargs):
        return {body}
"""
'@

Write-PyFile "app\generator\skill_generator.py" @'
from pathlib import Path
from .templates import SKILL_TEMPLATE

class SkillGenerator:

    def create(self, skill_name:str):
        cls = "".join(x.capitalize() for x in skill_name.split("_")) + "Skill"
        code = SKILL_TEMPLATE.format(
            class_name=cls,
            skill_name=skill_name,
            body=repr(f"{skill_name} executed")
        )

        folder = Path("app/skills/generated")
        folder.mkdir(parents=True, exist_ok=True)

        file = folder / f"{skill_name}.py"
        file.write_text(code, encoding="utf-8")
        return file
'@

Write-PyFile "app\generator\installer.py" @'
import importlib

class SkillInstaller:

    def install(self, module_name:str):
        return importlib.import_module(module_name)
'@

Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan
Write-Host " JARVIS SKILL GENERATOR READY" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
