from app.cortex.entity_extractor import EntityExtractor
from app.cortex.intent_detector import Intent

extractor = EntityExtractor()

tests = [
    ("open chrome", Intent.OPEN_APPLICATION),
    ("close notepad", Intent.CLOSE_APPLICATION),
    ("search python tutorials", Intent.SEARCH_WEB),
    ("how are you", Intent.CHAT),
]

for text, intent in tests:
    print(text)
    print(extractor.extract(text, intent))
    print("-" * 40)