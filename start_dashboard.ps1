$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$App = Join-Path $ProjectRoot "app\streamlit_app.py"
$LogDir = Join-Path $ProjectRoot "logs"

if (!(Test-Path $Python)) {
    Write-Host "Cannot find virtualenv Python: $Python" -ForegroundColor Red
    Write-Host "Please run: python -m venv .venv ; .venv\Scripts\pip install -r requirements.txt"
    Read-Host "Press Enter to exit"
    exit 1
}

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

function Test-PortFree {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -eq $conn
}

$Port = 8501
while (!(Test-PortFree -Port $Port)) {
    $Port += 1
}

$Url = "http://localhost:$Port"
$OutLog = Join-Path $LogDir "streamlit_quick_start.log"
$ErrLog = Join-Path $LogDir "streamlit_quick_start.err.log"

Write-Host "Starting Tech ETF Quant dashboard..." -ForegroundColor Green
Write-Host "URL: $Url" -ForegroundColor Cyan

Start-Process `
    -FilePath $Python `
    -ArgumentList @("-m", "streamlit", "run", $App, "--server.address", "localhost", "--server.port", "$Port") `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -WindowStyle Hidden

Start-Sleep -Seconds 5
Start-Process $Url

Write-Host ""
Write-Host "Dashboard is opening in your browser." -ForegroundColor Green
Write-Host "Close this window whenever you like; the dashboard process will keep running in the background."
Read-Host "Press Enter to close this launcher"
