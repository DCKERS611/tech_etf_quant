@echo off
setlocal EnableExtensions

cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "APP=%PROJECT_ROOT%\app\streamlit_app.py"
set "LOG_DIR=%PROJECT_ROOT%\logs"

if not exist "%PYTHON%" (
  echo Cannot find Python venv:
  echo %PYTHON%
  echo.
  echo Please run:
  echo python -m venv .venv
  echo .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "%APP%" (
  echo Cannot find Streamlit app:
  echo %APP%
  pause
  exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo Closing old dashboard and scheduler...
wmic process where "CommandLine like '%%tech_etf_quant.cli%%schedule%%--loop%%'" delete >nul 2>nul
wmic process where "CommandLine like '%%streamlit%%run%%streamlit_app.py%%'" delete >nul 2>nul
wmic process where "CommandLine like '%%app\\streamlit_app.py%%'" delete >nul 2>nul

for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R ":850[1-9] :8510"') do (
  taskkill /PID %%p /F >nul 2>nul
)

echo Starting background scheduler...
start "Tech ETF Scheduler" /min cmd /c ""%PYTHON%" -m tech_etf_quant.cli schedule --loop >> "%LOG_DIR%\scheduler.log" 2>> "%LOG_DIR%\scheduler.err.log""

echo Starting web dashboard...
start "Tech ETF Dashboard" /min cmd /c ""%PYTHON%" -m streamlit run "%APP%" --server.address localhost --server.port 8501 >> "%LOG_DIR%\dashboard.log" 2>> "%LOG_DIR%\dashboard.err.log""

echo Waiting for dashboard...
timeout /t 8 /nobreak >nul
start "" "http://localhost:8501"

echo.
echo Opened: http://localhost:8501
echo If the browser did not open, copy this URL into your browser.
echo Logs: %LOG_DIR%
pause
