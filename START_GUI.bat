@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found on PATH.
    pause
    exit /b 1
)

set TARGET=%~1
if "%TARGET%"=="" set TARGET=%~dp0kidcode

if not exist "%TARGET%" mkdir "%TARGET%" 2>nul

start "" pythonw "%~dp0gui.py" "%TARGET%"
