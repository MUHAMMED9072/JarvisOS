from .router import AIRouter

class AIManager:
    def __init__(self):
        self.router = AIRouter()

    def ask(self, provider, prompt):
        return self.router.ask(provider, prompt)
