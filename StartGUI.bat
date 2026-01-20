@echo off
chcp 65001 >nul
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python 3.7+
    pause
    exit /b 1
)

start "" pythonw.exe ngrok_gui.py
