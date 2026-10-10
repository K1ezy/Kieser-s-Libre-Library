@echo off
title Libre Library Launcher
echo ===================================================
echo             Starting Libre-Library
echo ===================================================

:: 1. Check Python Virtual Environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in .venv!
    pause
    exit /b
)

:: 2. Terminate stale processes holding port 8080 or ngrok tunnel
echo [*] Cleaning stale port 8080 and existing ngrok tunnel...
taskkill /F /IM ngrok.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

:: 3. Launch Libre-Library in a new window
echo [1/2] Launching Libre-Library Web App on port 8080...
start "Libre Library Server" cmd /k ".venv\Scripts\python.exe main.py"

:: 3. Wait a moment for server initialization
timeout /t 3 /nobreak >nul

:: 4. Launch Ngrok Tunnel
echo [2/2] Launching Ngrok Tunnel for public web access...
if exist "ngrok.exe" (
    start "Ngrok Tunnel" cmd /k "ngrok.exe http 8080 --host-header=rewrite"
) else (
    echo [WARNING] ngrok.exe not found in root directory!
)

echo.
echo ===================================================
echo [ONLINE] Local access:  http://localhost:8080
echo [ONLINE] Public access: Check the Ngrok window URL!
echo ===================================================
timeout /t 5
