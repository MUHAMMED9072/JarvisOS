# ==========================================
# JARVIS AI Module Bootstrap
# Creates the AI Router architecture
# ==========================================

$Base = "app\ai"

New-Item -ItemType Directory -Force -Path $Base | Out-Null
New-Item -ItemType Directory -Force -Path "$Base\providers" | Out-Null

$Files = @(
"__init__.py",
"router.py",
"manager.py",
"providers\__init__.py",
"providers\claude.py",
"providers\openai.py",
"providers\ollama.py",
"providers\deepseek.py",
"providers\gemini.py"
)

foreach($File in $Files){

    $Path = Join-Path $Base $File
    $Dir = Split-Path $Path

    New-Item -ItemType Directory -Force -Path $Dir | Out-Null

    if(!(Test-Path $Path)){

@"
"""
JARVIS AI Module

File: $File
"""
"@ | Set-Content $Path -Encoding UTF8

        Write-Host "Created $File" -ForegroundColor Green
    }
    else{
        Write-Host "Exists  $File" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "===================================" -ForegroundColor Cyan
Write-Host " AI MODULE BOOTSTRAP COMPLETE" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

Get-ChildItem $Base -Recurse
