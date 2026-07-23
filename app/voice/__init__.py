"""Voice subsystem for JARVIS OS.

Captures microphone audio, transcribes it via Whisper, and feeds the
resulting text into the existing Cortex pipeline. VoiceManager is the
sole orchestrator; every other module is a single-responsibility
helper.
"""
