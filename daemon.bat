@echo off
title StreamClip AI - Always On Launcher
echo ===================================================
echo   STREAMCLIP AI - PERSISTENT MODE
echo ===================================================

:: Kill existing
powershell -Command "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue; Stop-Process -Id (Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue"

echo Starting Backend...
start "StreamClip Backend" cmd /k "python main.py"

echo Starting Frontend...
cd frontend
start "StreamClip Frontend" cmd /k "npm.cmd run dev"

echo ===================================================
echo   SYSTEMS ARE RUNNING IN WATCH MODE
echo   Backend will auto-restart on code changes!
echo ===================================================
pause
