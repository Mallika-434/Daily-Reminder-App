@echo off
cd /d "%~dp0"
echo Starting RoutineAI...
echo.
python routineai.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Could not start routineai.py
    echo Make sure Python is installed and ANTHROPIC_API_KEY is set in .env
    pause
)
