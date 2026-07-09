class VoiceManager:
    def __init__(self):
        self.enabled = False

    def start(self):
        self.enabled = True
        print("Voice Engine Started")

    def stop(self):
        self.enabled = False
        print("Voice Engine Stopped")

    def is_running(self):
        return self.enabled
    