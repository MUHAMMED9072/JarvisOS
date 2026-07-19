# JARVIS OS - Sandbox Upgrade v11 (Starter)
Write-Host "========================================="
Write-Host " JARVIS OS Sandbox Upgrade v11"
Write-Host "========================================="
Write-Host ""
Write-Host "Project Root: $PSScriptRoot"
Write-Host ""
Write-Host "This starter verifies the project location."
Write-Host ""

if (!(Test-Path "$PSScriptRoot\main.py")) {
    Write-Host "ERROR: main.py not found."
    Write-Host "Move this file into your C:\JarvisOS project root."
    exit 1
}

Write-Host "[OK] Project detected."
Write-Host ""
Write-Host "Next: replace app\evolution\sandbox.py with the upcoming full implementation."
