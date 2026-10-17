@echo off
setlocal enabledelayedexpansion
title Stop MyAcs Services
cd /d "%~dp0"

echo ================================================================
echo               Stopping All MyAcs Services...
echo ================================================================
echo.

:: 1. Terminate all running MyAcs python/pythonw processes
echo [*] Terminating MyAcs background service processes...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

:: 2. Also check if any rogue process is still occupying port 45821
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :45821 ^| findstr LISTENING') do (
    if not "%%a"=="" (
        taskkill /f /pid %%a >nul 2>&1
    )
)

:: 3. Brief wait for socket cleanup
ping -n 2 127.0.0.1 >nul

echo.
echo ================================================================
echo            All MyAcs Services have been STOPPED!
echo ================================================================
echo.
echo   * Screen mirroring: STOPPED
echo   * Background tray:  STOPPED
echo   * Network ports:    RELEASED
echo   * PC performance:   100%% normal and untouched
echo.
echo ================================================================
echo.
ping -n 3 127.0.0.1 >nul
exit
