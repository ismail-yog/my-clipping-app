@echo off
title StreamClipper Manager
echo ===================================================
echo   StreamClipper - Automated Server Launcher
echo ===================================================
echo.
echo Starting StreamClipper Backend (Port 8000)...
start "StreamClipper Backend" cmd /k "python main.py"

echo.
echo Starting StreamClipper Frontend (Port 3000)...
cd /d "%~dp0frontend"
start "StreamClipper Frontend" cmd /k "npm run dev"

echo.
echo ===================================================
echo   All servers started successfully!
echo   You can close this launcher window.
echo   The backend and frontend will keep running.
echo ===================================================
pause
