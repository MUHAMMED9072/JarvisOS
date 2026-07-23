from __future__ import annotations

from app.ai.router import AIRouter
from app.core.config import Config
from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.core.registry import ServiceRegistry
from app.cortex.brains.deep_brain import DeepBrain
from app.cortex.brains.fast_brain import FastBrain
from app.cortex.brains.smart_brain import SmartBrain
from app.cortex.dispatcher import Dispatcher
from app.cortex.pipeline import CortexPipeline
from app.memory import MemoryManager
from app.skills.loader import SkillLoader
from app.skills.manager import SkillManager
from app.voice.config import VoiceConfig
from app.voice.manager import VoiceManager


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

        self.voice_manager: VoiceManager | None = None

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

        self.registry.register(
            "ai_router",
            AIRouter(),
        )

        self.registry.register(
            "fast_brain",
            FastBrain(self.registry),
        )

        self.registry.register(
            "smart_brain",
            SmartBrain(self.registry),
        )

        self.registry.register(
            "deep_brain",
            DeepBrain(self.registry),
        )

        # --------------------------------------------------
        # Voice configuration is registered *before* the
        # VoiceManager is constructed so the manager can read it
        # from the registry rather than importing the global
        # ``Config``. This keeps the dependency direction one-way:
        # voice -> core, never the reverse.
        # --------------------------------------------------

        self.registry.register(
            "voice_config",
            VoiceConfig(),
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

        # --------------------------------------------------
        # VoiceManager depends on cortex, dispatcher, and
        # event_bus. It must therefore be built last. It is a
        # no-op when ``VOICE.enabled`` is False (the default).
        # --------------------------------------------------

        self.voice_manager = VoiceManager(self.registry)

        self.registry.register(
            "voice_manager",
            self.voice_manager,
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
        self.logger.info(
            f"Voice Subsystem: "
            f"{'Enabled' if Config.VOICE.enabled else 'Disabled'}"
        )
        self.logger.info("Kernel Ready")

        # Start voice *after* the registry is fully populated. The
        # manager itself checks the config and silently no-ops when
        # disabled, so we don't need a separate branch here.
        if self.voice_manager is not None:
            self.voice_manager.start()

    def shutdown(self):

        self.logger.info("Shutting down JARVIS OS")

        if self.voice_manager is not None:
            self.voice_manager.stop()

        self.running = False
