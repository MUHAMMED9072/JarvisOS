from dotenv import load_dotenv
import os

load_dotenv()

class DeepSeekProvider:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")

    def generate(self, prompt:str)->str:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured in .env")
        raise NotImplementedError("Implement SDK call for DeepSeek")
