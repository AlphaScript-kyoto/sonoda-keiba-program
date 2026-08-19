@echo off
REM Debug / interactive console. For Task Scheduler use start_check_watch_heartbeat.vbs (no black window).
setlocal EnableExtensions
cd /d "%~dp0.."
set "PYTHONUNBUFFERED=1"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ERROR: .venv not found. Run: python -m venv .venv
    exit /b 1
)

echo [heartbeat] watch process health check (run every 20 min)
"%VENV_PY%" scripts\check_watch_heartbeat.py %*
exit /b %ERRORLEVEL%
