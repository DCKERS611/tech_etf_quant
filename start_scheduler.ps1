$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$PidFile = Join-Path $LogDir "scheduler.pid"
$OutLog = Join-Path $LogDir "scheduler.log"
$ErrLog = Join-Path $LogDir "scheduler.err.log"

if (!(Test-Path $Python)) {
    Write-Host "Cannot find virtualenv Python: $Python" -ForegroundColor Red
    Write-Host "Please run: python -m venv .venv ; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

if (Test-Path $PidFile) {
    $ExistingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($ExistingPid) {
        $ExistingProcess = Get-Process -Id ([int]$ExistingPid) -ErrorAction SilentlyContinue
        if ($ExistingProcess) {
            Write-Host "Scheduler is already running. PID: $ExistingPid" -ForegroundColor Yellow
            exit 0
        }
    }
}

Write-Host "Starting Tech ETF Quant scheduler in background..." -ForegroundColor Green
$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList @("-m", "tech_etf_quant.cli", "schedule", "--loop") `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -WindowStyle Hidden `
    -PassThru

$Process.Id | Set-Content -Path $PidFile -Encoding ascii
Write-Host "Scheduler started. PID: $($Process.Id)" -ForegroundColor Green
Write-Host "Log: $OutLog"
Write-Host "Error log: $ErrLog"
