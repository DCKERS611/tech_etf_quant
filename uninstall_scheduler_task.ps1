$ErrorActionPreference = "Stop"

$TaskName = "TechETFQuantScheduler"
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed Windows scheduled task: $TaskName" -ForegroundColor Green
} else {
    Write-Host "Scheduled task not found: $TaskName" -ForegroundColor Yellow
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StopScript = Join-Path $ProjectRoot "stop_scheduler.ps1"
if (Test-Path $StopScript) {
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StopScript
}
