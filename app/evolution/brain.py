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
        print("âœ“ User approval received")
        print("âœ“ Creating evolution plan")
        print("âœ“ AI generation: (coming in v2)")
        print("âœ“ Sandbox: (coming in v2)")
        print("âœ“ Tests: (coming in v2)")
        print("âœ“ Ready for next upgrade")
        return True
