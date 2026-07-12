# ==========================================
# JARVIS AI Core Installer
# ==========================================

function Write-PyFile($Path, $Content) {
    $Dir = Split-Path $Path
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    Set-Content -Path $Path -Value $Content -Encoding UTF8
    Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\ai\manager.py" @'
from .router import AIRouter

class AIManager:
    def __init__(self):
        self.router = AIRouter()

    def ask(self, provider, prompt):
        return self.router.ask(provider, prompt)
'@

Write-PyFile "app\ai\router.py" @'
from .providers.ollama import OllamaProvider
from .providers.openai import OpenAIProvider
from .providers.claude import ClaudeProvider
from .providers.gemini import GeminiProvider
from .providers.deepseek import DeepSeekProvider

class AIRouter:
    def __init__(self):
        self.providers = {
            "ollama": OllamaProvider(),
            "openai": OpenAIProvider(),
            "claude": ClaudeProvider(),
            "gemini": GeminiProvider(),
            "deepseek": DeepSeekProvider(),
        }

    def ask(self, provider, prompt):
        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}")
        return self.providers[provider].generate(prompt)
'@

$providers = @{
"ollama.py"="class OllamaProvider:`n    def generate(self,prompt):`n        raise NotImplementedError('Connect Ollama API here')"
"openai.py"="class OpenAIProvider:`n    def generate(self,prompt):`n        raise NotImplementedError('Connect OpenAI API here')"
"claude.py"="class ClaudeProvider:`n    def generate(self,prompt):`n        raise NotImplementedError('Connect Claude API here')"
"gemini.py"="class GeminiProvider:`n    def generate(self,prompt):`n        raise NotImplementedError('Connect Gemini API here')"
"deepseek.py"="class DeepSeekProvider:`n    def generate(self,prompt):`n        raise NotImplementedError('Connect DeepSeek API here')"
}

foreach($k in $providers.Keys){
    Write-PyFile ("app\ai\providers\" + $k) $providers[$k]
}

Write-Host ""
Write-Host "AI Core Installed." -ForegroundColor Cyan
