from app.cortex.brain_selector import BrainSelector
from app.cortex.intent_detector import Intent

selector = BrainSelector()

tests = [
    Intent.OPEN_APPLICATION,
    Intent.CLOSE_APPLICATION,
    Intent.SEARCH_WEB,
    Intent.CHAT,
    Intent.UNKNOWN,
]

for intent in tests:
    brain = selector.select(intent)
    print(f"{intent.value} -> {brain.value}")