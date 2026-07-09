import sounddevice as sd
import soundfile as sf


class VoiceListener:

    def record(
        self,
        filename="temp.wav",
        seconds=5,
        sample_rate=16000,
    ):

        print("Listening...")

        audio = sd.rec(
            int(seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )

        sd.wait()

        sf.write(filename, audio, sample_rate)

        print("Recording Finished")

        return filename