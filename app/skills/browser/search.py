from app.skills.base import Skill
from app.skills.result import SkillResult


class BrowserSearch(Skill):

    name = "Browser Search"
    intent = "search_web"
    version = "1.0.0"
    description = "Search the web"

    def run(self, request):

        query = request.entities.get(
            "query",
            ""
        )

        return SkillResult.ok(
            f"Searching for: {query}"
        )