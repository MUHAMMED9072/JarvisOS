from faster_whisper import WhisperModel


class WhisperProvider:

    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        print("Loading Whisper model...")

        self.model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )

        print("Whisper Ready")

    def transcribe(self, audio_file: str) -> str:

        segments, _ = self.model.transcribe(audio_file)

        text = ""

        for segment in segments:
            text += segment.text + " "

        return text.strip()
