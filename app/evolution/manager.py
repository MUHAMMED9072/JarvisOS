from .brain import EvolutionBrain

class EvolutionManager:
    def run(self):
        return EvolutionBrain().evolve()

if __name__=="__main__":
    EvolutionManager().run()
