@echo off
title StreamClip AI - Launcher
echo ===================================================
echo   STREAMCLIP AI - Starting Backend and Frontend
echo ===================================================

:: 1. Start the Backend (FastAPI + Pipeline)
echo Starting Backend...
start "StreamClip Backend" cmd /k "python main.py"

:: 2. Start the Frontend (Next.js)
echo Starting Frontend...
cd frontend
start "StreamClip Frontend" cmd /k "npm run dev"

echo.
echo ===================================================
echo   ALL SYSTEMS STARTING...
echo   Backend: http://localhost:8000
echo   Frontend: http://localhost:3000
echo ===================================================
echo.
pause
