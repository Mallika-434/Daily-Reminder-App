@echo off
cd /d "%~dp0"
python app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Could not run app.py
    echo Make sure Python is installed and added to PATH.
    pause
)
