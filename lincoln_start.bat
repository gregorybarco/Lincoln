@echo off
setlocal

REM ============================================================
REM  Lincoln v0.7.0 -- Navigator
REM  One-click launcher: activates venv, starts Flask, opens browser
REM  Place in: B:\Homebrewed_AI\Lincoln\
REM  To pin to taskbar: create a shortcut to this .bat with lincoln.ico
REM ============================================================

set LINCOLN_ROOT=%~dp0
set PORT=5000

REM Change to Lincoln root directory
cd /d "%LINCOLN_ROOT%"

REM Activate virtual environment
if not exist "venv\Scripts\activate.bat" (
    echo [Lincoln] ERROR: venv not found at %LINCOLN_ROOT%venv
    echo [Lincoln] Run: python -m venv venv ^&^& venv\Scripts\activate ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Start Flask in a minimized terminal window (stays open for live log output)
REM /min keeps it in the taskbar -- click it any time to see Lincoln's console output
start /min "Lincoln AI" cmd /k "python -m lincoln.app"

REM Poll until Flask is accepting connections (max 30 seconds)
echo [Lincoln] Starting... (waiting for port %PORT%)
set /a attempts=0

:POLL
set /a attempts+=1
if %attempts% gtr 60 (
    echo [Lincoln] WARNING: Flask did not start within 30 seconds.
    echo [Lincoln] Check the Lincoln AI terminal window for errors.
    goto OPEN
)

REM Check if port is open using PowerShell
powershell -command "try { $c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', %PORT%); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto POLL
)

:OPEN
echo [Lincoln] Ready. Opening http://127.0.0.1:%PORT%
start "" "http://127.0.0.1:%PORT%"

endlocal
