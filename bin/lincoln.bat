@echo off
cd /d B:\Homebrewed_AI\Lincoln
call venv\Scripts\activate

echo.
echo Starting Lincoln...
echo.

:: Open browser after a short delay to let Flask start
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"

:: Start the Flask application
python -m lincoln.app

:end
