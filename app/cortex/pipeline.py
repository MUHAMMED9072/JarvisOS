from __future__ import annotations

from .input_manager import InputManager
from .normalizer import Normalizer
from .intent_detector import IntentDetector
from .entity_extractor import EntityExtractor
from .brain_selector import BrainSelector


class CortexPipeline:
    """
    Complete Cortex processing pipeline.
    """

    def __init__(self):
        self.input = InputManager()
        self.normalizer = Normalizer()
        self.intent_detector = IntentDetector()
        self.entity_extractor = EntityExtractor()
        self.brain_selector = BrainSelector()

    def process(self, text: str, source: str = "voice"):
        # Step 1: Create request
        request = self.input.receive(text, source)

        # Step 2: Normalize
        request.normalized = self.normalizer.process(request.text)

        # Step 3: Detect intent
        intent, confidence = self.intent_detector.detect(request.normalized)
        request.intent = intent.value
        request.confidence = confidence

        # Step 4: Extract entities
        request.entities = self.entity_extractor.extract(
            request.normalized,
            intent,
        )

        # Step 5: Select brain
        request.brain = self.brain_selector.select(intent).value

        # Return the completed request
        return request