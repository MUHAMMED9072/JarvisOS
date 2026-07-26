from .brain import EvolutionBrain


class EvolutionManager:

    def __init__(self, registry=None):
        self._registry = registry

    def run(self):
        return EvolutionBrain(self._registry).evolve()


if __name__ == "__main__":
    EvolutionManager().run()
