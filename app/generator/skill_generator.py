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
