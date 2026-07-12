from dotenv import load_dotenv
import os

load_dotenv()

class GeminiProvider:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")

    def generate(self, prompt:str)->str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured in .env")
        raise NotImplementedError("Implement SDK call for Gemini")
