"""Voice-Cortex integration layer.

:class:`VoiceCortexIntegration` bridges the voice subsystem with the
Cortex pipeline and dispatcher, preserving voice metadata and
managing conversation sessions.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.registry import ServiceRegistry
from app.cortex.dispatcher import Dispatcher
from app.cortex.models import CortexResponse
from app.cortex.pipeline import CortexPipeline


class VoiceCortexIntegration:
    """Bridges transcribed speech into the Cortex AI pipeline.

    Flow::

        VoiceListener -> WhisperProvider -> VoiceCortexIntegration
            -> CortexPipeline -> Dispatcher -> Brain -> AIHandler -> AIManager

    Preserves voice metadata (confidence, session, timestamp) and
    tracks session-to-conversation mappings so that utterances in the
    same session reuse the same AI conversation.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        self._pipeline: CortexPipeline = registry.get("cortex")
        self._dispatcher: Dispatcher = registry.get("dispatcher")

    def process_speech(
        self,
        text: str,
        *,
        confidence: float = 0.0,
        session_id: str = "",
        source: str = "voice",
        session_metadata: dict[str, Any] | None = None,
    ) -> CortexResponse:
        """Process transcribed speech through Cortex.

        Parameters
        ----------
        text
            Transcribed speech text.
        confidence
            Transcription confidence (0.0–1.0).
        session_id
            Session identifier for conversation reuse.
        source
            Source label (default ``"voice"``).
        session_metadata
            Additional metadata for the response.

        Returns
        -------
        CortexResponse
            Response with full AI and voice metadata.
        """
        if not text or not text.strip():
            return CortexResponse(
                success=False,
                response="Empty transcription",
                metadata={
                    "error": "empty_transcript",
                    "transcript_confidence": confidence,
                    "source": source,
                },
            )

        text = text.strip()
        timestamp = time.time()

        try:
            request = self._pipeline.process(text, source=source)
            request.confidence = confidence
        except Exception as exc:
            return CortexResponse(
                success=False,
                response=f"Cortex pipeline error: {exc}",
                metadata={
                    "error": "pipeline_failure",
                    "transcript_confidence": confidence,
                    "source": source,
                    "timestamp": timestamp,
                },
            )

        try:
            skill_result, cortex_response = self._dispatcher.dispatch_with_response(
                request,
            )
        except Exception as exc:
            return CortexResponse(
                success=False,
                response=f"Dispatch error: {exc}",
                metadata={
                    "error": "dispatch_failure",
                    "transcript_confidence": confidence,
                    "source": source,
                    "timestamp": timestamp,
                },
            )

        meta: dict[str, Any] = {
            "transcript_confidence": confidence,
            "source": source,
            "timestamp": timestamp,
        }
        if cortex_response.metadata:
            meta.update(cortex_response.metadata)
        if session_id:
            meta["session_id"] = session_id
        if session_metadata:
            meta.update(session_metadata)

        return CortexResponse(
            success=skill_result.success,
            response=str(skill_result.message),
            provider=cortex_response.provider,
            model=cortex_response.model,
            routing_strategy=cortex_response.routing_strategy,
            conversation_id=cortex_response.conversation_id,
            template_name=cortex_response.template_name,
            metadata=meta,
        )
