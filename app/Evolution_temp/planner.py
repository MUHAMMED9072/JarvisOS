class EvolutionPlanner:
    def create_plan(self, scan):
        plan=[]
        if scan["files"]<100:
            plan.append("Increase modularity")
        plan += [
            "Dynamic Skill Loader",
            "Semantic Memory Search",
            "AI Retry Logic",
            "Plugin API"
        ]
        return plan
