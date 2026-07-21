@echo off
setlocal

REM ============================================================
REM  Lincoln v0.6.0 -- Create Windows shortcuts
REM  Run once after deployment to add Lincoln to Start Menu + Desktop
REM  Usage: .\lincoln_create_shortcut.bat  (from PowerShell)
REM         lincoln_create_shortcut.bat    (from cmd)
REM ============================================================

set "LINCOLN_ROOT=%~dp0"
set "LINCOLN_BAT=%LINCOLN_ROOT%lincoln_start.bat"
set "LINCOLN_ICO=%LINCOLN_ROOT%lincoln.ico"
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "START_LINK=%START_MENU%\Lincoln.lnk"
set "DESKTOP_LINK=%USERPROFILE%\Desktop\Lincoln.lnk"

if not exist "%LINCOLN_BAT%" (
    echo [Lincoln] ERROR: lincoln_start.bat not found at %LINCOLN_BAT%
    echo [Lincoln] Make sure lincoln_start.bat is in the same folder as this script.
    pause
    exit /b 1
)

echo [Lincoln] Creating Start Menu shortcut...
powershell -NoProfile -NonInteractive -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%START_LINK%'); $s.TargetPath = '%LINCOLN_BAT%'; $s.WorkingDirectory = '%LINCOLN_ROOT%'; $s.IconLocation = '%LINCOLN_ICO%'; $s.Description = 'Lincoln AI Assistant'; $s.Save()"

if errorlevel 1 (
    echo [Lincoln] WARNING: Could not create Start Menu shortcut.
) else (
    echo [Lincoln] Start Menu shortcut created.
)

echo [Lincoln] Creating Desktop shortcut...
powershell -NoProfile -NonInteractive -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP_LINK%'); $s.TargetPath = '%LINCOLN_BAT%'; $s.WorkingDirectory = '%LINCOLN_ROOT%'; $s.IconLocation = '%LINCOLN_ICO%'; $s.Description = 'Lincoln AI Assistant'; $s.Save()"

if errorlevel 1 (
    echo [Lincoln] WARNING: Could not create Desktop shortcut.
) else (
    echo [Lincoln] Desktop shortcut created.
)

echo.
echo [Lincoln] Done. Search 'Lincoln' in Start Menu or use the Desktop icon.
echo [Lincoln] To pin to taskbar: right-click the Start Menu entry, Pin to taskbar.
echo.
pause
endlocal
