@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "PYTHONUNBUFFERED=1"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ERROR: .venv not found
    exit /b 1
)

echo [line-webhook] Capture team user IDs when members message the bot
echo [line-webhook] Next: ngrok http 8080  and set webhook URL in LINE Developers
echo.
"%VENV_PY%" scripts\line_webhook_server.py
exit /b %ERRORLEVEL%
