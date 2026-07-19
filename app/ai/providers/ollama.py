from ollama import chat

class OllamaProvider:
    def generate(self, prompt:str, model="qwen2.5-coder"):
        r = chat(
            model=model,
            messages=[{"role":"user","content":prompt}]
        )
        return r["message"]["content"]
