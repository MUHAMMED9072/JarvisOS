# ==========================================
# JARVIS AI Providers Installer
# ==========================================

function Write-PyFile($Path, $Content) {
    $Dir = Split-Path $Path
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    Set-Content -Path $Path -Value $Content -Encoding UTF8
    Write-Host "Installed $Path" -ForegroundColor Green
}

$provider = @'
from dotenv import load_dotenv
import os

load_dotenv()

class {CLASS}:
    def __init__(self):
        self.api_key = os.getenv("{KEY}")

    def generate(self, prompt:str)->str:
        if not self.api_key:
            raise RuntimeError("{KEY} is not configured in .env")
        raise NotImplementedError("Implement SDK call for {NAME}")
'@

Write-PyFile "app\ai\providers\openai.py" ($provider.Replace("{CLASS}","OpenAIProvider").Replace("{KEY}","OPENAI_API_KEY").Replace("{NAME}","OpenAI"))
Write-PyFile "app\ai\providers\claude.py" ($provider.Replace("{CLASS}","ClaudeProvider").Replace("{KEY}","ANTHROPIC_API_KEY").Replace("{NAME}","Claude"))
Write-PyFile "app\ai\providers\gemini.py" ($provider.Replace("{CLASS}","GeminiProvider").Replace("{KEY}","GEMINI_API_KEY").Replace("{NAME}","Gemini"))
Write-PyFile "app\ai\providers\deepseek.py" ($provider.Replace("{CLASS}","DeepSeekProvider").Replace("{KEY}","DEEPSEEK_API_KEY").Replace("{NAME}","DeepSeek"))

$ollama = @'
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
'@

Write-PyFile "app\ai\providers\ollama.py" $ollama

Write-Host ""
Write-Host "AI Providers Installed." -ForegroundColor Cyan
