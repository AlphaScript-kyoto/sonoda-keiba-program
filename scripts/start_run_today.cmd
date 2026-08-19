@echo off
REM Debug / interactive console. For Task Scheduler use start_run_today.vbs (no black window).
setlocal EnableExtensions
cd /d "%~dp0.."
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ERROR: .venv not found
    exit /b 1
)
echo [run-today] fetch_daily + LINE (schedule for 21:00 Task Scheduler)
"%VENV_PY%" run_today.py
exit /b %ERRORLEVEL%
