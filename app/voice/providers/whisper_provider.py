from faster_whisper import WhisperModel


class WhisperProvider:

    def __init__(self, model_name: str = "base"):
        print("Loading Whisper model...")

        self.model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
        )

        print("Whisper Ready")

    def transcribe(self, audio_file: str) -> str:

        segments, _ = self.model.transcribe(audio_file)

        text = ""

        for segment in segments:
            text += segment.text + " "

        return text.strip()
    