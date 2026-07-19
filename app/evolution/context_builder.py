from pathlib import Path

class ContextBuilder:

    def build(self, root="app"):
        lines=["PROJECT TREE"]
        for p in sorted(Path(root).rglob("*.py")):
            lines.append(str(p).replace("\\\\","/"))
        Path("data").mkdir(exist_ok=True)
        out=Path("data/project_tree.txt")
        out.write_text("\\n".join(lines),encoding="utf-8")
        return out
