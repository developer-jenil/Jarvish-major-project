@echo off
title JARVIS Public Web Link Generator
cd /d "%~dp0"

echo ====================================================
echo   J.A.R.V.I.S. Public Web Link Generator
echo ====================================================
echo.
echo 1. Starting JARVIS Local Server...
if exist ".\venv\Scripts\python.exe" (
    start "JARVIS Server" /min ".\venv\Scripts\python.exe" server.py
) else (
    start "JARVIS Server" /min python server.py
)

timeout /t 3 /nobreak >nul

echo 2. Generating Secure Public HTTPS Link...
echo.
echo ----------------------------------------------------
echo Copy and share the URL shown below with anyone:
echo (Make sure to keep this window open while sharing)
echo ----------------------------------------------------
echo.

npx --yes localtunnel --port 5000
pause
