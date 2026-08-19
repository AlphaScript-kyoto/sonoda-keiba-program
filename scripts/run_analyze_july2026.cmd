@echo off
REM July 2026 review launcher (double-click or from cmd)
setlocal
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\analyze_july2026.py" %*
) else (
  echo .venv not found. Run: python -m venv .venv
  python "scripts\analyze_july2026.py" %*
)
echo.
pause
