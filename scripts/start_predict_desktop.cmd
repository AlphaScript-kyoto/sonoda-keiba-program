@echo off
cd /d "%~dp0.."
REM Debug console launcher. Prefer start_predict_desktop.vbs (no black window).
".venv\Scripts\python.exe" app\predict_desktop.py
if errorlevel 1 pause