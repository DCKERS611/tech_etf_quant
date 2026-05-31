$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ProjectRoot "logs"
$PidFile = Join-Path $LogDir "scheduler.pid"

if (!(Test-Path $PidFile)) {
    Write-Host "No scheduler.pid found. Scheduler may not be running." -ForegroundColor Yellow
    exit 0
}

$PidText = Get-Content $PidFile -ErrorAction SilentlyContinue
if (!$PidText) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Empty scheduler.pid removed." -ForegroundColor Yellow
    exit 0
}

$Process = Get-Process -Id ([int]$PidText) -ErrorAction SilentlyContinue
if ($Process) {
    Stop-Process -Id $Process.Id -Force
    Write-Host "Scheduler stopped. PID: $PidText" -ForegroundColor Green
} else {
    Write-Host "Scheduler process was not running. PID: $PidText" -ForegroundColor Yellow
}

Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
