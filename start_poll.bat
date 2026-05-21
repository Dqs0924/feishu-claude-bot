@echo off
chcp 65001 >nul
title 飞书-ClaudeCode 调度系统

set "PROJECT_DIR=%~dp0"
set "LOG=%PROJECT_DIR%feishu_poll.log"
set "RESTART_DELAY=5"

:loop
echo ============================================
echo   飞书 - Claude Code 远程智能调度系统
echo   启动时间：%date% %time%
echo   项目目录：%PROJECT_DIR%
echo   日志文件：%LOG%
echo ============================================
echo [%date% %time%] 服务启动 >> "%LOG%"

cd /d "%PROJECT_DIR%"

:: 自动探测 Python（优先 py 启动器，其次 PATH 中 python）
set "PYTHON_CMD=py -3.11"
py -3.11 -c "import sys; sys.exit(0)" >nul 2>&1
if errorlevel 1 (
    set "PYTHON_CMD=py -3"
    py -3 -c "import sys; sys.exit(0)" >nul 2>&1
    if errorlevel 1 (
        set "PYTHON_CMD=python"
        python -c "import sys; sys.exit(0)" >nul 2>&1
        if errorlevel 1 (
            echo [错误] 未找到 Python，请确认 Python 3.11+ 已安装并在 PATH 中
            echo 按任意键退出...
            pause >nul
            exit /b 1
        )
    )
)

echo 使用 Python：%PYTHON_CMD%
%PYTHON_CMD% -u run_feishu_poll.py 2>&1

echo [%date% %time%] 服务退出（退出码：%ERRORLEVEL%），%RESTART_DELAY%秒后重启... >> "%LOG%"
echo.
echo 服务已退出，%RESTART_DELAY%秒后自动重启...
echo 按 Ctrl+C 可中止重启循环...
timeout /t %RESTART_DELAY% /nobreak >nul

goto loop
