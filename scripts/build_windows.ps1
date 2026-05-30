$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

if (Test-Path ".venv\Scripts\python.exe") {
    $PythonBin = ".venv\Scripts\python.exe"
} else {
    $PythonBin = "python"
}

& $PythonBin -m pip install -r requirements.txt -r requirements-build.txt

$Version = (Select-String -Path "定格截图.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

& $PythonBin -m PyInstaller `
    --noconfirm `
    --windowed `
    --name "定格截图" `
    --icon "assets\app.ico" `
    --add-data "assets;assets" `
    "定格截图.py"

Copy-Item "dist\定格截图\定格截图.exe" "dist\定格截图-v$Version-Windows.exe" -Force
Compress-Archive -Path "dist\定格截图" -DestinationPath "dist\定格截图-v$Version-Windows.zip" -Force

Write-Host "Windows app: dist\定格截图\定格截图.exe"
Write-Host "Windows exe: dist\定格截图-v$Version-Windows.exe"
Write-Host "Windows zip: dist\定格截图-v$Version-Windows.zip"
