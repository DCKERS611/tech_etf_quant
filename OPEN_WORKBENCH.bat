@echo off
chcp 65001 >nul
setlocal

set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "APP=%PROJECT_ROOT%app\streamlit_app.py"
set "LOG_DIR=%PROJECT_ROOT%logs"

if not exist "%PYTHON%" (
  echo 找不到 Python 虚拟环境：
  echo %PYTHON%
  echo.
  echo 请先在项目目录运行：
  echo python -m venv .venv
  echo .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "%APP%" (
  echo 找不到网页主程序：
  echo %APP%
  pause
  exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo 正在启动 A股科技ETF量化工作台...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = '%PROJECT_ROOT%';" ^
  "$py = '%PYTHON%';" ^
  "$app = '%APP%';" ^
  "$log = '%LOG_DIR%';" ^
  "$schedulerPid = Join-Path $log 'scheduler.pid';" ^
  "$dashboardPid = Join-Path $log 'dashboard.pid';" ^
  "function Test-Pid($file) { if (!(Test-Path $file)) { return $false }; $pidText = Get-Content $file -ErrorAction SilentlyContinue; if (!$pidText) { return $false }; return $null -ne (Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue) };" ^
  "if (!(Test-Pid $schedulerPid)) { $p = Start-Process -FilePath $py -ArgumentList @('-m','tech_etf_quant.cli','schedule','--loop') -WorkingDirectory $root -RedirectStandardOutput (Join-Path $log 'scheduler.log') -RedirectStandardError (Join-Path $log 'scheduler.err.log') -WindowStyle Hidden -PassThru; $p.Id | Set-Content -Path $schedulerPid -Encoding ascii; Write-Host ('后台自动刷新已启动，进程号：' + $p.Id) -ForegroundColor Green } else { Write-Host '后台自动刷新已经在运行。' -ForegroundColor Yellow };" ^
  "if (Test-Pid $dashboardPid) { Write-Host '网页面板已经在运行，正在打开浏览器。' -ForegroundColor Yellow; Start-Process 'http://localhost:8501'; exit 0 };" ^
  "$port = 8501; while (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { $port += 1 };" ^
  "$url = 'http://localhost:' + $port;" ^
  "$d = Start-Process -FilePath $py -ArgumentList @('-m','streamlit','run',$app,'--server.address','localhost','--server.port',([string]$port)) -WorkingDirectory $root -RedirectStandardOutput (Join-Path $log 'dashboard.log') -RedirectStandardError (Join-Path $log 'dashboard.err.log') -WindowStyle Hidden -PassThru;" ^
  "$d.Id | Set-Content -Path $dashboardPid -Encoding ascii;" ^
  "Start-Sleep -Seconds 5;" ^
  "Start-Process $url;" ^
  "Write-Host ('网页面板已打开：' + $url) -ForegroundColor Green;"

echo.
echo 已完成。你可以关闭这个窗口，后台刷新和网页服务会继续运行。
echo 日志目录：%LOG_DIR%
pause
