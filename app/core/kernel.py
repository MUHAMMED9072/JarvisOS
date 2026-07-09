from app.events import event_bus
from app.services import logger, registry


class JarvisKernel:

    VERSION = "0.2.0-alpha"

    def __init__(self):
        self.registry = registry
        self.event_bus = event_bus
        self.logger = logger
        self.running = False

    def boot(self):
        self.logger.info("=" * 50)
        self.logger.info("Starting JARVIS OS")
        self.logger.info("Version %s", self.VERSION)

        self.running = True

        self.logger.info("Service Registry Ready")
        self.logger.info("Event Bus Ready")
        self.logger.info("Kernel Ready")

    def shutdown(self):
        self.logger.info("Shutting down JARVIS")
        self.running = False
        