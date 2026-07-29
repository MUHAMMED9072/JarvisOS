from pathlib import Path

from .templates import SKILL_TEMPLATE
from app.ads.paths import GENERATED_DIR


class SkillGenerator:

    def create(
        self,
        skill_name: str,
        intent: str,
        description: str = "",
    ) -> Path:

        if not intent:
            raise ValueError(
                f"Cannot generate skill '{skill_name}' without a non-empty intent."
            )

        cls = "".join(x.capitalize() for x in skill_name.split("_")) + "Skill"

        code = SKILL_TEMPLATE.format(
            class_name=cls,
            skill_name=skill_name,
            intent=intent,
            description=description or f"Auto-generated skill: {skill_name}",
            body=repr(f"{skill_name} executed"),
        )

        folder = GENERATED_DIR / "skills"
        folder.mkdir(parents=True, exist_ok=True)

        init_file = folder / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")

        file = folder / f"{skill_name}.py"
        file.write_text(code, encoding="utf-8")
        return file