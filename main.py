"""
MyAcs — Local Network Screen Mirroring Application
Main Entry Point for Windows 10/11.

Usage:
    python main.py              # Launch desktop application and background service
    python main.py --background # Launch silently to system tray (used by Windows Startup)
    python main.py --headless   # Run as a pure headless daemon/service
"""

import os
import sys
import time
import argparse
import threading
import signal

# Ensure package root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Handle pythonw.exe execution where stdout and stderr are None
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

from myacs.core.device_identity import config
from myacs.core.discovery import lan_discovery
from myacs.core.streaming_server import run_server
from myacs.service.autostart import is_windows_autostart_enabled, set_windows_autostart


def start_background_services(port: int = 45821):
    """Starts the streaming server and LAN discovery service in daemon threads."""
    # 1. Start LAN UDP discovery
    lan_discovery.start()

    # 2. Start Uvicorn HTTP & WebSocket streaming server in background thread
    server_thread = threading.Thread(
        target=run_server,
        kwargs={"host": "0.0.0.0", "port": port},
        daemon=True,
        name="MyAcsStreamingServer"
    )
    server_thread.start()
    print(f"[MyAcs] Core streaming engine active on port {port}")


def main():
    parser = argparse.ArgumentParser(description="MyAcs Local Network Screen Mirroring")
    parser.add_argument("--background", action="store_true", help="Start silently in background tray without showing window")
    parser.add_argument("--headless", action="store_true", help="Run in headless service mode without GUI")
    parser.add_argument("--port", type=int, default=config.get("port", 45821), help="Streaming server port")
    args = parser.parse_args()

    print("=" * 60)
    print(" MyAcs — Local Network Screen Mirroring (View-Only)")
    print(f" Permanent Device ID: {config.get('device_id')}")
    print(f" Security PIN:        {config.get('security_pin')}")
    print(f" Mode:                {'Headless' if args.headless else ('Background Tray' if args.background else 'Desktop Window')}")
    print("=" * 60)

    # Check and enforce auto-start if configured in settings
    if config.get("autostart", True) and not is_windows_autostart_enabled():
        set_windows_autostart(True)

    # Start network streaming and discovery
    start_background_services(port=args.port)

    # Mode 1: Pure headless daemon
    if args.headless:
        print("[MyAcs] Running in headless mode. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[MyAcs] Stopping services...")
            lan_discovery.stop()
            sys.exit(0)

    # Mode 2: Desktop Window + System Tray (PySide6)
    try:
        from PySide6.QtWidgets import QApplication
        from myacs.service.tray_app import MyAcsMainWindow, MyAcsTrayManager

        app = QApplication(sys.argv)
        app.setApplicationName("MyAcs")
        app.setQuitOnLastWindowClosed(False)  # Keep running when window is closed!

        window = MyAcsMainWindow(port=args.port)
        tray_manager = MyAcsTrayManager(window, app)

        if not args.background:
            window.show()
        else:
            print("[MyAcs] Running in background. Active in Windows System Tray.")

        ret = app.exec()
        lan_discovery.stop()
        sys.exit(ret)

    except Exception as e:
        print(f"[MyAcs] GUI initialization error: {e}")
        print("[MyAcs] Continuing in headless background server mode...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            lan_discovery.stop()
            sys.exit(0)


if __name__ == "__main__":
    main()
