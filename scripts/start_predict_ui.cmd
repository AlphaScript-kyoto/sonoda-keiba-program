@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "PYTHONUNBUFFERED=1"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto run

echo [predict-ui] .venv not found. Creating virtual environment...
where py >nul 2>&1
if %errorlevel% equ 0 goto venv_py
python -m venv .venv
goto venv_done
:venv_py
py -3 -m venv .venv
:venv_done
if not exist "%VENV_PY%" (
    echo ERROR: Failed to create .venv
    exit /b 1
)
echo [predict-ui] Installing dependencies (first time may take several minutes)...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed
    exit /b 1
)

:run
echo.
echo [predict-ui] Starting Streamlit (first start may take 10-30 seconds on OneDrive)...
echo [predict-ui] URL: http://127.0.0.1:8501
echo [predict-ui] Browser opens once when the server is ready.
echo.
REM 127.0.0.1 bind avoids WinError 64 on some Windows setups. Browser: Streamlit only (no duplicate tab).
"%VENV_PY%" -m streamlit run app\predict_app.py --server.address 127.0.0.1 --server.port 8501
exit /b %ERRORLEVEL%
