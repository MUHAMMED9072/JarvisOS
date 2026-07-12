# ==========================================
# JARVIS Calculator Skill Installer
# ==========================================

function Write-PyFile($Path, $Content) {
    $Dir = Split-Path $Path
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    Set-Content -Path $Path -Value $Content -Encoding UTF8
    Write-Host "Installed $Path" -ForegroundColor Green
}

$code = @'
import math
import re

class CalculatorSkill:
    name = "calculator"

    def run(self, text: str):
        t = text.lower().strip()

        m = re.search(r"add (\d+(?:\.\d+)?) and (\d+(?:\.\d+)?)", t)
        if m:
            return float(m.group(1)) + float(m.group(2))

        m = re.search(r"subtract (\d+(?:\.\d+)?) from (\d+(?:\.\d+)?)", t)
        if m:
            return float(m.group(2)) - float(m.group(1))

        m = re.search(r"multiply (\d+(?:\.\d+)?) (?:by )?(\d+(?:\.\d+)?)", t)
        if m:
            return float(m.group(1)) * float(m.group(2))

        m = re.search(r"divide (\d+(?:\.\d+)?) by (\d+(?:\.\d+)?)", t)
        if m:
            return float(m.group(1)) / float(m.group(2))

        m = re.search(r"square root of (\d+(?:\.\d+)?)", t)
        if m:
            return math.sqrt(float(m.group(1)))

        m = re.search(r"power (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)", t)
        if m:
            return float(m.group(1)) ** float(m.group(2))

        return "Unknown calculation"

if __name__ == "__main__":
    s = CalculatorSkill()
    print(s.run("add 5 and 10"))
    print(s.run("multiply 8 by 7"))
    print(s.run("square root of 81"))
'@

Write-PyFile "app\skills\generated\calculator.py" $code

Write-Host ""
Write-Host "Calculator Skill Installed" -ForegroundColor Cyan
