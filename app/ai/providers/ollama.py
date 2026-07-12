from dotenv import load_dotenv
import os

load_dotenv()

class OllamaProvider:
    def __init__(self):
        self.host = os.getenv("OLLAMA_HOST","http://localhost:11434")

    def generate(self, prompt:str)->str:
        import ollama
        client = ollama.Client(host=self.host)
        response = client.chat(
            model="llama3.1",
            messages=[{"role":"user","content":prompt}]
        )
        return response["message"]["content"]
