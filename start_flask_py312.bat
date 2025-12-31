@echo off
REM Start Flask with Python 3.12 (GPU support)

echo ============================================================
echo Starting Flask Backend with Python 3.12 (GPU Enabled)
echo ============================================================
echo.

REM Check if Python 3.12 is available
py -3.12 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python 3.12 not found!
    echo Please install Python 3.12 from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Python 3.12 detected!
echo.

REM Start Flask with Python 3.12
py -3.12 app.py

pause

