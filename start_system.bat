@echo off
REM Start script for AIVMS Backend System

echo.
echo ============================================================
echo AIVMS Backend System Startup
echo ============================================================
echo.

REM Kill any existing processes
echo Cleaning up old processes...
taskkill /IM mediamtx.exe /F >nul 2>&1
taskkill /IM python.exe /F >nul 2>&1
timeout /t 2 /nobreak

REM Check if ports are free
echo.
echo Checking if ports are available...
netstat -ano | findstr ":8888" >nul
if %errorlevel% equ 0 (
    echo WARNING: Port 8888 is still in use!
    echo Waiting 5 seconds...
    timeout /t 5 /nobreak
)

netstat -ano | findstr ":3000" >nul
if %errorlevel% equ 0 (
    echo WARNING: Port 3000 is still in use!
    echo Waiting 5 seconds...
    timeout /t 5 /nobreak
)

REM Start MediaMTX
echo.
echo ============================================================
echo Starting MediaMTX on port 8888...
echo ============================================================
echo.
start "MediaMTX" cmd /k "mediamtx.exe"

REM Wait for MediaMTX to start
echo Waiting for MediaMTX to initialize...
timeout /t 3 /nobreak

REM Start Flask
echo.
echo ============================================================
echo Starting Flask Backend on port 3000...
echo ============================================================
echo.
start "Flask Backend" cmd /k "python app.py"

REM Wait for Flask to start
echo Waiting for Flask to initialize...
timeout /t 3 /nobreak

REM Open browser
echo.
echo ============================================================
echo Opening Dashboard in browser...
echo ============================================================
echo.
timeout /t 2 /nobreak
start http://localhost:3000/dashboard.html

echo.
echo ============================================================
echo System started!
echo ============================================================
echo.
echo MediaMTX: http://localhost:8888
echo Flask API: http://localhost:3000
echo Dashboard: http://localhost:3000/dashboard.html
echo.
echo Press Ctrl+C in either window to stop the service.
echo.
pause

