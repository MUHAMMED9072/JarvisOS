from app.cortex.intent_detector import IntentDetector

detector = IntentDetector()

tests = [
    "open chrome",
    "close chrome",
    "search python tutorials",
    "how are you",
]

for text in tests:
    intent, confidence = detector.detect(text)
    print(f"{text} -> {intent.value} ({confidence})")