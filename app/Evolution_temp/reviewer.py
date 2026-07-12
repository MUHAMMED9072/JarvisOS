class Reviewer:
    def review(self,plan):
        return {
            "risk":"LOW",
            "changes":len(plan),
            "approved":False
        }
