function Write-PyFile($Path,$Content){
$Dir=Split-Path $Path
New-Item -ItemType Directory -Force -Path $Dir|Out-Null
Set-Content -Path $Path -Value $Content -Encoding UTF8
Write-Host "Installed $Path"
}

Write-PyFile "app\evolution\manager.py" @'
from .brain import EvolutionBrain

class EvolutionManager:
    def run(self):
        return EvolutionBrain().evolve()

if __name__=="__main__":
    EvolutionManager().run()
'@

Write-Host "Evolution Manager Installed"
