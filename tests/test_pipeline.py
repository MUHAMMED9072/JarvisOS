from pprint import pprint

from app.cortex.pipeline import CortexPipeline

pipeline = CortexPipeline()

request = pipeline.process(
    text="Jarvis, what was the last application I opened?",
    source="voice"
)

pprint(request)