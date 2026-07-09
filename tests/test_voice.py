from app.voice.listener import VoiceListener
from app.voice.providers.whisper_provider import WhisperProvider


listener = VoiceListener()

audio = listener.record()

whisper = WhisperProvider("base")

text = whisper.transcribe(audio)

print("\nRecognized:\n")

print(text)