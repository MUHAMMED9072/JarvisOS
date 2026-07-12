from pathlib import Path

class ProjectScanner:
    def scan(self, root="app"):
        files=list(Path(root).rglob("*.py"))
        return {
            "files": len(files),
            "paths":[str(f) for f in files]
        }
