@echo off
:: Batch script to add Windows Defender Firewall rules for MyAcs
:: Self-elevates to Administrator if not already elevated
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges to configure Windows Firewall...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

title MyAcs Windows Firewall Configuration
echo ========================================================
echo  Configuring Windows Defender Firewall for MyAcs
echo ========================================================
echo.

echo Adding TCP Inbound Rule for Port 45821 (Screen Streaming)...
netsh advfirewall firewall delete rule name="MyAcs Screen Mirroring" >nul 2>&1
netsh advfirewall firewall add rule name="MyAcs Screen Mirroring" dir=in action=allow protocol=TCP localport=45821 profile=any description="Allows incoming screen mirroring connections for MyAcs"

echo Adding UDP Inbound Rule for Port 45820 (LAN Peer Discovery)...
netsh advfirewall firewall delete rule name="MyAcs LAN Discovery" >nul 2>&1
netsh advfirewall firewall add rule name="MyAcs LAN Discovery" dir=in action=allow protocol=UDP localport=45820 profile=any description="Allows peer discovery beacons for MyAcs on local network"

echo.
echo ========================================================
echo  Firewall rules added successfully!
echo  Other PCs on your local network can now connect.
echo ========================================================
timeout /t 5
