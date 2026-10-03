@echo off
setlocal
cd /d "%~dp0"

REM  Watch a folder of Luau and report, in plain words, what is wrong with it.
REM
REM  Drag a folder onto this file to watch that folder, or run it and it watches
REM  .\kidcode next to this file.

if not exist "luaucheck.py" goto MISSING
if not exist "tools\luau-ast.exe" goto NOTOOLS

where python >nul 2>&1
if %errorlevel% neq 0 goto NOPYTHON

set TARGET=%~1
if "%TARGET%"=="" set TARGET=%~dp0kidcode

if not exist "%TARGET%" (
    mkdir "%TARGET%" 2>nul
    echo.
    echo   Made a folder called kidcode.
    echo   Put the .luau files in there and run this again.
    echo   Or drag any folder onto this file.
    echo.
    pause
    exit /b 0
)

echo.
echo   CodeCoach is watching:
echo     %TARGET%
echo.
echo   Save a file and this refreshes. Ctrl-C to stop.
echo.
python "luaucheck.py" --watch --folder "%TARGET%"
pause
exit /b 0

:MISSING
echo.
echo   luaucheck.py was not found next to this file.
echo   Keep the whole folder together.
echo.
pause
exit /b 1

:NOTOOLS
echo.
echo   tools\luau-ast.exe is missing.
echo.
echo   Download the Luau release from
echo     https://github.com/luau-lang/luau/releases
echo   and put luau.exe and luau-ast.exe in the tools folder.
echo.
pause
exit /b 1

:NOPYTHON
echo.
echo   Python was not found on PATH.
echo   Install Python 3 from python.org, then run this again.
echo.
pause
exit /b 1
