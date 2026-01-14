@echo off
chcp 65001 >nul
title Sunny-Ngrok GUI 管理器

echo ========================================
echo   Sunny-Ngrok GUI 管理器
echo ========================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.7+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [信息] 正在启动 GUI 管理器...
echo.

REM 启动 GUI
start pythonw ngrok_gui.py
exit
