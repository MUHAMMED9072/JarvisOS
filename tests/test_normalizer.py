from app.cortex.normalizer import Normalizer

normalizer = Normalizer()

tests = [
    "Jarvis, Open Chrome!",
    "HEY JARVIS launch chrome",
    "ok jarvis run notepad",
    "Execute calculator",
]

for text in tests:
    print(normalizer.process(text))