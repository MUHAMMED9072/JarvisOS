"""Smoke test: kernel boots with voice subsystem wired in.

These tests exercise the real :class:`JarvisKernel` boot path to
verify the voice subsystem is registered correctly. They do not
flip ``VOICE.enabled`` (that path is covered by the
``test_manager.py`` lifecycle tests).
"""

from __future__ import annotations

from app.core.kernel import JarvisKernel
from app.voice.config import VoiceConfig
from app.voice.manager import VoiceManager


class TestKernelVoiceIntegration:
    def test_voice_disabled_by_default(self):
        """Kernel boots and voice_manager is a no-op when disabled."""
        k = JarvisKernel()
        k.boot()
        try:
            assert k.registry.exists("voice_manager")
            assert k.registry.exists("voice_config")
            assert isinstance(k.voice_manager, VoiceManager)
            assert k.voice_manager.is_running() is False
            config = k.registry.get("voice_config")
            assert isinstance(config, VoiceConfig)
            assert config.enabled is False
        finally:
            k.shutdown()
        assert k.voice_manager.is_running() is False

    def test_voice_manager_uses_registry_cortex_and_dispatcher(self):
        """The manager resolves cortex + dispatcher from the registry."""
        k = JarvisKernel()
        k.boot()
        try:
            # Trigger lazy dependency resolution
            k.voice_manager._ensure_dependencies()
            assert k.voice_manager._cortex is k.cortex
            assert k.voice_manager._dispatcher is k.dispatcher
            assert k.voice_manager._event_bus is k.event_bus
        finally:
            k.shutdown()
