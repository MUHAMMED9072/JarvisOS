# ==========================================
# JARVIS Evolution Approval Upgrade
# ==========================================

function Write-PyFile($Path,$Content){
 $Dir=Split-Path $Path
 New-Item -ItemType Directory -Force -Path $Dir|Out-Null
 Set-Content -Path $Path -Value $Content -Encoding UTF8
 Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .reviewer import Reviewer

class EvolutionBrain:

    def evolve(self):
        scan = ProjectScanner().scan()
        plan = EvolutionPlanner().create_plan(scan)
        review = Reviewer().review(plan)

        print("="*45)
        print("JARVIS EVOLUTION REPORT")
        print("="*45)
        print(f"Python Files : {scan['files']}")
        print()
        print("Suggested Upgrades:")
        for i,p in enumerate(plan,1):
            print(f"{i}. {p}")
        print()
        print(f"Risk : {review['risk']}")
        print("="*45)

        choice = input("Proceed with evolution? (Y/N): ").strip().upper()

        if choice != "Y":
            print("Evolution cancelled.")
            return False

        print()
        print("✓ User approval received")
        print("✓ Creating evolution plan")
        print("✓ AI generation: (coming in v2)")
        print("✓ Sandbox: (coming in v2)")
        print("✓ Tests: (coming in v2)")
        print("✓ Ready for next upgrade")
        return True
'@

Write-Host ""
Write-Host "Evolution Approval Installed" -ForegroundColor Cyan
