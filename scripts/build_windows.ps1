$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

if (Test-Path ".venv\Scripts\python.exe") {
    $PythonBin = ".venv\Scripts\python.exe"
} else {
    $PythonBin = "python"
}

& $PythonBin -m pip install -r requirements.txt -r requirements-build.txt

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

& $PythonBin -m PyInstaller `
    --noconfirm `
    --windowed `
    --name "定格截图" `
    --icon "assets\app.ico" `
    --add-data "assets;assets" `
    "定格截图.py"

Compress-Archive -Path "dist\定格截图" -DestinationPath "dist\定格截图-Windows.zip" -Force

Write-Host "Windows app: dist\定格截图\定格截图.exe"
Write-Host "Windows zip: dist\定格截图-Windows.zip"
