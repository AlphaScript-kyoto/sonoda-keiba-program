@echo off
REM Debug / interactive console. For Task Scheduler use start_watch_race_day.vbs (no black window).
setlocal EnableExtensions
cd /d "%~dp0.."
set "PYTHONUNBUFFERED=1"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ERROR: .venv not found. Run: python -m venv .venv
    exit /b 1
)

echo [watch-race-day] Sonoda schedule + snapshots T-30/20/10 + LINE at T-10
echo [watch-race-day] Press Ctrl+C to stop. No races today exits quickly.
echo.
"%VENV_PY%" scripts\watch_race_day.py %*
exit /b %ERRORLEVEL%
