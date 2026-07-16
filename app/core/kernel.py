from __future__ import annotations

from app.core.config import Config
from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.core.registry import ServiceRegistry
from app.cortex.dispatcher import Dispatcher
from app.cortex.pipeline import CortexPipeline
from app.memory import MemoryManager
from app.skills.loader import SkillLoader
from app.skills.manager import SkillManager


class JarvisKernel:

    VERSION = Config.VERSION

    def __init__(self):

        self.logger = JarvisLogger

        self.registry = ServiceRegistry()

        self.event_bus = EventBus()

        self.skill_manager = SkillManager()

        self.skill_loader = SkillLoader()

        self.memory = MemoryManager()

        self.cortex = CortexPipeline()

        self.dispatcher: Dispatcher | None = None

        self.running = False

    def boot(self):

        self.logger.info("=" * 60)
        self.logger.info(f"Starting {Config.APP_NAME}")
        self.logger.info(f"Version {self.VERSION}")

        # --------------------------------------------------
        # Register Core Services FIRST
        # --------------------------------------------------

        self.registry.register(
            "skill_manager",
            self.skill_manager
        )

        self.registry.register(
            "event_bus",
            self.event_bus
        )

        self.registry.register(
            "memory",
            self.memory
        )

        self.registry.register(
            "cortex",
            self.cortex
        )

        # --------------------------------------------------
        # Load Skills AFTER services exist
        # --------------------------------------------------

        self.skill_loader.load(
            self.skill_manager,
            self.registry
        )

        # --------------------------------------------------
        # Dispatcher reads skill_manager/memory from the registry
        # at construction time, so it must be built after both
        # are registered above.
        # --------------------------------------------------

        self.dispatcher = Dispatcher(self.registry)

        self.registry.register(
            "dispatcher",
            self.dispatcher
        )

        self.running = True

        self.logger.info("Configuration Loaded")
        self.logger.info("Service Registry Ready")
        self.logger.info("Event Bus Ready")
        self.logger.info("Memory Engine Ready")
        self.logger.info("Cortex Pipeline Ready")
        self.logger.info("Skill Loader Ready")
        self.logger.info(
            f"{len(self.skill_manager.skills)} Skills Loaded"
        )
        self.logger.info("Dispatcher Ready")
        self.logger.info("Kernel Ready")

    def shutdown(self):

        self.logger.info("Shutting down JARVIS OS")

        self.running = False