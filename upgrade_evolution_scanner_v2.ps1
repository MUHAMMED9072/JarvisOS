# ==========================================
# JARVIS Evolution Scanner v2
# ==========================================

function Write-PyFile($Path,$Content){
 $Dir=Split-Path $Path
 New-Item -ItemType Directory -Force -Path $Dir|Out-Null
 Set-Content -Path $Path -Value $Content -Encoding UTF8
 Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\evolution\scanner.py" @'
from pathlib import Path
import ast
import json

class ProjectScanner:

    def scan(self, root="app"):
        report={
            "python_files":[],
            "classes":[],
            "functions":[],
            "imports":[]
        }

        for file in Path(root).rglob("*.py"):
            report["python_files"].append(str(file))
            try:
                source=file.read_text(encoding="utf-8")
                tree=ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        report["classes"].append(node.name)
                    elif isinstance(node, ast.FunctionDef):
                        report["functions"].append(node.name)
                    elif isinstance(node,(ast.Import,ast.ImportFrom)):
                        report["imports"].append(ast.unparse(node))
            except Exception:
                pass

        report["summary"]={
            "files":len(report["python_files"]),
            "classes":len(report["classes"]),
            "functions":len(report["functions"]),
            "imports":len(report["imports"])
        }

        Path("data").mkdir(exist_ok=True)
        with open("data/evolution_report.json","w",encoding="utf-8") as f:
            json.dump(report,f,indent=2)

        return report
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner

class EvolutionBrain:

    def evolve(self):
        scan=ProjectScanner().scan()

        s=scan["summary"]

        print("="*50)
        print("JARVIS EVOLUTION REPORT")
        print("="*50)
        print(f"Python Files : {s['files']}")
        print(f"Classes      : {s['classes']}")
        print(f"Functions    : {s['functions']}")
        print(f"Imports      : {s['imports']}")
        print()
        print("Report saved -> data/evolution_report.json")
        print("="*50)
        return scan
'@

Write-Host ""
Write-Host "Evolution Scanner v2 Installed" -ForegroundColor Cyan
