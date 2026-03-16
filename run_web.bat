@echo off
cd /d "%~dp0"
echo Starting Daily Schedule web server...
echo.
python web_app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Could not start web_app.py
    echo Make sure Python is installed and added to PATH.
    pause
)
