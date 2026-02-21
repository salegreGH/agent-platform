
Set-ExecutionPolicy -Scope Process Bypass -Force
cd "$PSScriptRoot\.."

python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt

Write-Host "Instal·lat. Executa .\scripts\run.bat i obre http://127.0.0.1:8787"
