from __future__ import annotations

import atexit
import signal

from app.ai.conversation import ConversationManager
from app.ai.diagnostics import AIDiagnosticsService, MetricsCollector
from app.ai.manager import AIManager
from app.ai.memory_integration import MemoryAwareAI
from app.ai.router import AIRouter
from app.ai.services import PlanningService, ReasoningService, StructuredService
from app.ai.templates import PromptTemplateRegistry
from app.ai.tools import ToolRegistry
from app.core.config import Config
from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.core.registry import ServiceRegistry
from app.plugins.sdk import PluginLoader, PluginManager
from app.cortex.brains.deep_brain import DeepBrain
from app.cortex.brains.fast_brain import FastBrain
from app.cortex.brains.smart_brain import SmartBrain
from app.cortex.dispatcher import Dispatcher
from app.cortex.pipeline import CortexPipeline
from app.memory import MemoryManager
from app.evolution.ai import EvolutionAI as EvolutionAI_Service
from app.skills.loader import SkillLoader
from app.skills.manager import SkillManager
from app.voice.config import VoiceConfig
from app.voice.integration import VoiceCortexIntegration
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

        atexit.register(self.shutdown)
        signal.signal(signal.SIGINT, self._signal_handler)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
        except AttributeError:
            pass

    def _signal_handler(self, signum: int, _frame) -> None:
        self.logger.info("Received signal %d, shutting down...", signum)
        self.shutdown()

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
        # AI Services – created here so they are shared
        # singletons that every consumer receives via the
        # registry.
        # --------------------------------------------------

        _metrics_collector = MetricsCollector()
        _ai_router = AIRouter(metrics_collector=_metrics_collector)
        _conv_manager = ConversationManager()
        _template_registry = PromptTemplateRegistry()
        _tool_registry = ToolRegistry()

        self.registry.register("metrics_collector", _metrics_collector)
        self.registry.register("ai_router", _ai_router)
        self.registry.register("conversation_manager", _conv_manager)
        self.registry.register("template_registry", _template_registry)
        self.registry.register("tool_registry", _tool_registry)

        self.registry.register(
            "ai_manager",
            AIManager(
                event_bus=self.event_bus,
                conversation_manager=_conv_manager,
                template_registry=_template_registry,
                router=_ai_router,
                metrics_collector=_metrics_collector,
            ),
        )

        self.registry.register(
            "ai_diagnostics",
            AIDiagnosticsService(_metrics_collector),
        )

        self.registry.register(
            "structured_service",
            StructuredService(),
        )

        self.registry.register(
            "planning_service",
            PlanningService(),
        )

        self.registry.register(
            "reasoning_service",
            ReasoningService(),
        )

        self.registry.register(
            "memory_aware_ai",
            MemoryAwareAI(
                ai_manager=self.registry.get("ai_manager"),
                memory_manager=self.registry.get_optional("memory"),
            ),
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
        # Plugin SDK – discover third-party plugins after all
        # core services are registered.
        # --------------------------------------------------

        self.plugin_manager = PluginManager(self.registry)
        self.plugin_loader = PluginLoader(
            self.plugin_manager, self.registry,
        )

        self.registry.register(
            "plugin_manager",
            self.plugin_manager,
        )

        plugin_dir = Config.PLUGIN_DIR
        if plugin_dir.is_dir():
            self.plugin_loader.add_directory(plugin_dir)
        self.plugin_loader.load_all()

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

        self.registry.register(
            "voice_integration",
            VoiceCortexIntegration(self.registry),
        )

        self.registry.register(
            "evolution_ai",
            EvolutionAI_Service(self.registry),
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

        if not self.running:
            return

        self.logger.info("Shutting down JARVIS OS")

        if self.voice_manager is not None:
            self.voice_manager.stop()

        if hasattr(self, 'plugin_manager'):
            self.plugin_manager.shutdown_all()

        try:
            self.memory.storage.save(self.memory.storage.load())
        except Exception:
            self.logger.exception("Failed to flush memory during shutdown")

        self.running = False

        self.logger.info("Shutdown complete")
