@echo off
title JARVIS Neural Operating Interface
cd /d "%~dp0"
echo ====================================================
echo Starting J.A.R.V.I.S. Neural Web Interface...
echo ====================================================

if exist ".\venv\Scripts\python.exe" (
    start "" ".\venv\Scripts\python.exe" launch_ui.py
) else (
    echo [ERROR] Virtual environment not found at .\venv
    pause
)
