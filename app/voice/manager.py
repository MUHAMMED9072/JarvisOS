"""Voice orchestrator.

VoiceManager is the *only* component in the voice subsystem that
touches the rest of JARVIS. It pulls audio → text from
:class:`SpeechRecognizer`, hands the text to
:class:`~app.cortex.pipeline.CortexPipeline`, then forwards the
populated request to :class:`~app.cortex.dispatcher.Dispatcher`. The
dispatcher is responsible for everything that follows: memory,
brain selection, skill execution.

This class deliberately does **not**:

* parse intents (Cortex does that)
* select brains (the brain selector in Cortex does that)
* call skills directly (the dispatcher routes to the brain, which
  calls the skill)
* write to memory (the dispatcher already does)

It may speak the final response via :class:`Speaker`. It never raises
Cortex-level errors — they are caught and turned into a fail result.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.core.registry import ServiceRegistry
from app.cortex.dispatcher import Dispatcher
from app.cortex.models import CortexResponse
from app.cortex.pipeline import CortexPipeline
from app.skills.result import SkillResult
from app.voice.commands import CommandRouter
from app.voice.config import VoiceConfig
from app.voice.recognizer import SpeechRecognizer
from app.voice.speaker import Speaker
from app.voice.wakeword import WakeWordDetector


class VoiceManager:
    """The sole entry point of the voice subsystem.

    Construction is dependency-injected via the :class:`ServiceRegistry`
    so that the kernel can wire it alongside the rest of the system.
    """

    EVENT_TRANSCRIPT = "voice.transcript"
    EVENT_RESPONSE = "voice.response"
    EVENT_ERROR = "voice.error"
    EVENT_WAKE = "voice.wake"

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry
        self._config: VoiceConfig = self._load_config()
        self._logger = JarvisLogger

        # Late binding: these may be re-fetched after registry setup
        self._cortex: Optional[CortexPipeline] = None
        self._dispatcher: Optional[Dispatcher] = None
        self._event_bus: Optional[EventBus] = None

        # Voice-local collaborators
        self._recognizer = SpeechRecognizer(self._config)
        self._wakeword = WakeWordDetector(self._config)
        self._commands = CommandRouter(self._config)
        self._speaker = Speaker(self._config)

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    # ------------------------------------------------------------------
    # Configuration / dependency helpers
    # ------------------------------------------------------------------

    def _load_config(self) -> VoiceConfig:
        """Prefer the registry-injected ``voice_config`` when present."""
        try:
            if self._registry.exists("voice_config"):
                config = self._registry.get("voice_config")
                if isinstance(config, VoiceConfig):
                    return config
        except Exception:  # noqa: BLE001
            pass
        return VoiceConfig()

    def _ensure_dependencies(self) -> None:
        """Resolve cortex, dispatcher, and event bus on first use."""
        if self._cortex is None:
            self._cortex = self._registry.get("cortex")
        if self._dispatcher is None:
            self._dispatcher = self._registry.get("dispatcher")
        if self._event_bus is None and self._registry.exists("event_bus"):
            self._event_bus = self._registry.get("event_bus")
            self._speaker.set_event_bus(self._event_bus)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the voice subsystem.

        If ``VoiceConfig.enabled`` is False this is a no-op (the
        subsystem is dormant, e.g. in tests or headless runs).
        """
        if not self._config.enabled:
            self._logger.info("Voice subsystem disabled (config.enabled=False)")
            return

        if self._running:
            return

        self._ensure_dependencies()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="VoiceManager",
            daemon=True,
        )
        self._running = True
        self._thread.start()
        self._logger.info("Voice subsystem started")

    def stop(self) -> None:
        """Stop the background loop and wait for the thread to exit."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._running = False
        self._logger.info("Voice subsystem stopped")

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def listen_once(self, timeout: float | None = None) -> Optional[str]:
        """Capture a single utterance and return the transcript.

        Returns None if no speech was captured.
        """
        if timeout is not None and timeout > 0:
            # ``listen_and_transcribe`` is blocking; we accept that
            # for now. Callers that need a real timeout can wrap
            # this in their own thread.
            pass
        return self._recognizer.listen_and_transcribe()

    def handle_transcript(self, text: str) -> SkillResult:
        """Run a transcript through the cortex + dispatcher chain.

        This is the only place where the voice subsystem talks to the
        cortex. All routing decisions belong to Cortex / Dispatcher.
        """
        if text is None:
            return SkillResult.fail(message="No transcript provided")

        text = text.strip()
        if not text:
            return SkillResult.fail(message="Empty transcript")

        self._ensure_dependencies()
        assert self._cortex is not None
        assert self._dispatcher is not None

        if self._event_bus is not None:
            self._event_bus.publish(self.EVENT_TRANSCRIPT, text)

        # 1. Optional short-circuit for session commands
        if self._commands.is_command(text):
            result = self._commands.handle(text)
            if result is not None:
                self._maybe_speak(result.message)
                return result

        # 2. Cortex normalises, detects intent, extracts entities,
        #    and selects a brain.
        try:
            request = self._cortex.process(text, source="voice")
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Cortex pipeline failed: %s", exc)
            self._emit_error(exc)
            return SkillResult.fail(message=f"Cortex error: {exc}")

        # 3. Dispatcher handles memory + brain + skill.
        try:
            result = self._dispatcher.dispatch(request)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Dispatcher failed: %s", exc)
            self._emit_error(exc)
            return SkillResult.fail(message=f"Dispatcher error: {exc}")

        self._maybe_speak(result.message)
        return result

    def handle_transcript_with_response(
        self,
        text: str,
        *,
        confidence: float = 0.0,
        session_id: str = "",
        session_metadata: dict[str, Any] | None = None,
    ) -> tuple[SkillResult, CortexResponse]:
        """Run a transcript through cortex + dispatcher and return both
        the ``SkillResult`` and a ``CortexResponse`` with full metadata.

        This is the voice-aware equivalent of :meth:`handle_transcript`
        that additionally preserves transcription confidence, source,
        timestamp, and session metadata in the ``CortexResponse``.

        Voice metadata and error handling follow the same rules as
        :meth:`handle_transcript` — all exceptions are caught and
        returned as fail results.
        """
        if text is None:
            return (
                SkillResult.fail(message="No transcript provided"),
                CortexResponse(
                    success=False, response="No transcript provided",
                    metadata={"error": "empty_transcript"},
                ),
            )

        text = text.strip()
        if not text:
            return (
                SkillResult.fail(message="Empty transcript"),
                CortexResponse(
                    success=False, response="Empty transcript",
                    metadata={"error": "empty_transcript"},
                ),
            )

        self._ensure_dependencies()
        assert self._cortex is not None
        assert self._dispatcher is not None

        if self._event_bus is not None:
            self._event_bus.publish(self.EVENT_TRANSCRIPT, text)

        timestamp = time.time()

        # 1. Short-circuit for session commands
        if self._commands.is_command(text):
            result = self._commands.handle(text)
            if result is not None:
                self._maybe_speak(result.message)
                cr = CortexResponse(
                    success=True,
                    response=result.message,
                    metadata={
                        "source": "voice",
                        "command": True,
                        "timestamp": timestamp,
                        "session_id": session_id,
                    },
                )
                return result, cr

        # 2. Cortex pipeline
        try:
            request = self._cortex.process(text, source="voice")
            request.confidence = confidence
        except Exception as exc:
            self._logger.error("Cortex pipeline failed: %s", exc)
            self._emit_error(exc)
            return (
                SkillResult.fail(message=f"Cortex error: {exc}"),
                CortexResponse(
                    success=False, response=str(exc),
                    metadata={
                        "error": "pipeline_failure",
                        "transcript_confidence": confidence,
                        "source": "voice",
                        "timestamp": timestamp,
                        "session_id": session_id,
                    },
                ),
            )

        # 3. Dispatch with response
        try:
            result, cortex_response = self._dispatcher.dispatch_with_response(request)
        except Exception as exc:
            self._logger.error("Dispatcher failed: %s", exc)
            self._emit_error(exc)
            return (
                SkillResult.fail(message=f"Dispatcher error: {exc}"),
                CortexResponse(
                    success=False, response=str(exc),
                    metadata={
                        "error": "dispatch_failure",
                        "transcript_confidence": confidence,
                        "source": "voice",
                        "timestamp": timestamp,
                        "session_id": session_id,
                    },
                ),
            )

        # 4. Enrich metadata with voice information
        meta: dict[str, Any] = {
            "transcript_confidence": confidence,
            "source": "voice",
            "timestamp": timestamp,
        }
        if cortex_response.metadata:
            meta.update(cortex_response.metadata)
        if session_id:
            meta["session_id"] = session_id
        if session_metadata:
            meta.update(session_metadata)

        result_cr = CortexResponse(
            success=result.success,
            response=str(result.message),
            provider=cortex_response.provider,
            model=cortex_response.model,
            routing_strategy=cortex_response.routing_strategy,
            conversation_id=cortex_response.conversation_id,
            template_name=cortex_response.template_name,
            metadata=meta,
        )

        self._maybe_speak(result.message)
        return result, result_cr

    def speak(self, text: str) -> None:
        """Public entry point for speaking a piece of text."""
        self._maybe_speak(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Background loop.

        Iterates: wake-word (optional) → recognise → handle → pause.
        Exceptions inside the loop are caught and logged so the loop
        never silently dies.
        """
        assert self._config is not None
        pause = self._config.loop_pause_seconds

        while not self._stop_event.is_set():
            try:
                if self._config.wake_word_enabled:
                    heard = self._wait_for_wake_word()
                    if not heard:
                        continue
                    if self._event_bus is not None:
                        self._event_bus.publish(self.EVENT_WAKE, self._config.wake_word)

                transcript = self._recognizer.listen_and_transcribe()
                if not transcript:
                    self._stop_event.wait(pause)
                    continue

                self.handle_transcript(transcript)
                self._stop_event.wait(pause)
            except Exception as exc:  # noqa: BLE001 — keep loop alive
                self._logger.error("Voice loop error: %s", exc)
                self._emit_error(exc)
                self._stop_event.wait(pause)

    def _wait_for_wake_word(self) -> bool:
        """Listen for the wake word until detected or stopped.

        Stub implementation: this re-uses the recogniser in fixed
        duration mode and asks the wake-word detector to inspect the
        resulting frames. A real implementation will stream frames
        directly to ``WakeWordDetector.detect()``.
        """
        try:
            audio_path = self._recognizer._listener.record(
                seconds=2,
                sample_rate=self._config.sample_rate,
            )
            if not audio_path:
                return False

            # Cheap energy inspection on the recorded file
            try:
                import soundfile as sf  # local import
                data, _ = sf.read(audio_path, dtype="float32")
                return self._wakeword.detect(data)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("Wake-word inspection failed: %s", exc)
                return False
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Wake-word capture failed: %s", exc)
            return False

    def _maybe_speak(self, text: str) -> None:
        if not text:
            return
        try:
            self._speaker.speak(text)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Speaker failed: %s", exc)

    def _emit_error(self, exc: BaseException) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(self.EVENT_ERROR, str(exc))

    # ------------------------------------------------------------------
    # Test-friendly seams
    # ------------------------------------------------------------------

    def set_recognizer(self, recognizer: SpeechRecognizer) -> None:
        """Replace the recogniser (test seam)."""
        self._recognizer = recognizer

    def set_speaker(self, speaker: Speaker) -> None:
        """Replace the speaker (test seam)."""
        self._speaker = speaker
        if self._event_bus is not None:
            self._speaker.set_event_bus(self._event_bus)
