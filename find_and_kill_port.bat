@echo off
REM Script to find and kill processes using specific ports

echo.
echo ============================================================
echo PORT FINDER AND KILLER
echo ============================================================
echo.

REM Check port 5555
echo Checking port 5555...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5555"') do (
    echo Found process using port 5555: PID %%a
    echo Killing process %%a...
    taskkill /PID %%a /F
    echo Done!
)

REM Check port 6666
echo.
echo Checking port 6666...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":6666"') do (
    echo Found process using port 6666: PID %%a
    echo Killing process %%a...
    taskkill /PID %%a /F
    echo Done!
)

REM Check port 7777
echo.
echo Checking port 7777...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7777"') do (
    echo Found process using port 7777: PID %%a
    echo Killing process %%a...
    taskkill /PID %%a /F
    echo Done!
)

REM Check port 8888
echo.
echo Checking port 8888...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8888"') do (
    echo Found process using port 8888: PID %%a
    echo Killing process %%a...
    taskkill /PID %%a /F
    echo Done!
)

REM Check port 9999
echo.
echo Checking port 9999...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9999"') do (
    echo Found process using port 9999: PID %%a
    echo Killing process %%a...
    taskkill /PID %%a /F
    echo Done!
)

echo.
echo ============================================================
echo All ports cleared!
echo ============================================================
echo.
echo Now try starting MediaMTX:
echo   ./mediamtx.exe
echo.
pause

