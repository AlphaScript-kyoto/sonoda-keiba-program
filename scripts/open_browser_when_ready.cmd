@echo off
setlocal EnableExtensions
set "URL=http://localhost:8501"
for /l %%i in (1,1,45) do (
    powershell -NoProfile -Command "try{(New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',8501);exit 0}catch{exit 1}" >nul 2>&1
    if not errorlevel 1 (
        start "" "%URL%"
        exit /b 0
    )
    ping 127.0.0.1 -n 2 >nul
)
exit /b 1