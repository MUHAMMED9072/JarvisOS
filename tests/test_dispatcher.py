from pprint import pprint

from app.core.kernel import JarvisKernel
from app.cortex.dispatcher import Dispatcher
from app.cortex.pipeline import CortexPipeline

kernel = JarvisKernel()
kernel.boot()

pipeline = CortexPipeline()
dispatcher = Dispatcher(kernel.registry)

# Test memory recall
request = pipeline.process(
    text="Jarvis, what was the last application I opened?",
    source="voice"
)

pprint(request)
print()

result = dispatcher.dispatch(request)

print(result.success)
print(result.message)