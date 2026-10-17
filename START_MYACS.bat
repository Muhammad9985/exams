@echo off
setlocal enabledelayedexpansion
title MyAcs — All-in-One Service Launcher
cd /d "%~dp0"

echo ================================================================
echo               MyAcs — Screen Mirroring All-in-One Launcher
echo ================================================================
echo.

:: 1. Check Windows Defender Firewall rules
netsh advfirewall firewall show rule name="MyAcs Screen Mirroring" >nul 2>&1
if %errorLevel% neq 0 (
    net session >nul 2>&1
    if !errorLevel! equ 0 (
        echo [*] Registering Windows Defender Firewall rules for LAN access...
        netsh advfirewall firewall add rule name="MyAcs Screen Mirroring" dir=in action=allow protocol=TCP localport=45821 profile=any >nul 2>&1
        netsh advfirewall firewall add rule name="MyAcs LAN Discovery" dir=in action=allow protocol=UDP localport=45820 profile=any >nul 2>&1
    ) else (
        echo [*] Note: If other PCs on LAN cannot connect, run 'add_firewall_rule.bat' as Admin once.
    )
)

:: 2. Ensure Windows Autostart on Boot is registered
echo [*] Ensuring automatic Windows startup on boot is configured...
python -c "from myacs.service.autostart import set_windows_autostart; set_windows_autostart(True)" >nul 2>&1

:: 3. Query Device ID, PIN, and IP
for /f "tokens=*" %%i in ('python -c "from myacs.core.device_identity import config; print(config.get('device_id'))"') do set MY_DEVICE_ID=%%i
for /f "tokens=*" %%i in ('python -c "from myacs.core.device_identity import config; print(config.get('security_pin'))"') do set MY_PIN=%%i
for /f "tokens=*" %%i in ('python -c "from myacs.core.discovery import get_all_lan_ips; ips = get_all_lan_ips(); print(ips[0] if ips else '127.0.0.1')"') do set MY_LAN_IP=%%i

:: 4. Start the background service (if not already running)
echo [*] Starting MyAcs Background Service (Screen Streamer + LAN Discovery)...
python -c "import socket; s = socket.socket(); err = s.connect_ex(('127.0.0.1', 45821)); s.close(); exit(0 if err == 0 else 1)" >nul 2>&1
if %errorLevel% neq 0 (
    start "" pythonw main.py --background
)

:: Wait until server is fully initialized and accepting connections
echo [*] Waiting for MyAcs server to be ready...
python -c "import time, socket; [time.sleep(0.3) for _ in range(25) if socket.socket().connect_ex(('127.0.0.1', 45821)) != 0]" >nul 2>&1

:: 5. Open Web Viewer / Dashboard in default browser
echo [*] Opening MyAcs Dashboard in your web browser...
start http://127.0.0.1:45821

echo.
echo ================================================================
echo                MyAcs Services are FULLY ACTIVE!
echo ================================================================
echo.
echo   * Permanent Device ID:   !MY_DEVICE_ID!
echo   * Security PIN:          !MY_PIN!
echo.
echo   * This PC Browser URL:   http://127.0.0.1:45821
echo   * Other PCs on LAN URL:  http://!MY_LAN_IP!:45821
echo   * Direct 1-Click Stream: http://!MY_LAN_IP!:45821/view
echo.
echo   * Background Service:    RUNNING (in Windows System Tray)
echo   * Windows Auto-Start:    ENABLED (starts automatically on boot)
echo   * View-Only Mode:        ENFORCED (mouse/keyboard control blocked)
echo.
echo ================================================================
echo   You can close this window now. MyAcs remains active 24/7!
echo ================================================================
echo.
pause
