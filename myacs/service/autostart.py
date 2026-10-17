"""
MyAcs — Windows Autostart & Background Service Manager
Ensures MyAcs launches automatically at Windows boot and continues running
seamlessly in the background even after window closure or system restarts.
"""

import os
import sys
import subprocess
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "MyAcsScreenMirror"


def get_launch_command() -> str:
    """Returns the exact command to launch MyAcs in background mode."""
    # If compiled as standalone executable:
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        return f'"{exe_path}" --background'
    
    # If running from python source:
    # Use pythonw.exe so no console window flashes at Windows startup!
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    
    main_py = Path(__file__).resolve().parent.parent.parent / "main.py"
    return f'"{pythonw}" "{main_py}" --background'


def is_windows_autostart_enabled() -> bool:
    """Checks whether the Windows Registry Run key exists for MyAcs."""
    if not winreg:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
    except Exception:
        return False


def set_windows_autostart(enable: bool = True) -> bool:
    """Registers or unregisters MyAcs in the Windows Startup registry."""
    if not winreg:
        return False
    
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_ALL_ACCESS) as key:
            if enable:
                cmd = get_launch_command()
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                print(f"[Autostart] Enabled Windows auto-start: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    print("[Autostart] Disabled Windows auto-start.")
                except FileNotFoundError:
                    pass
        
        # Also ensure Startup folder batch file backup for maximum reliability
        _sync_startup_folder(enable)
        return True
    except Exception as e:
        print(f"[Autostart] Registry error: {e}")
        return False


def _sync_startup_folder(enable: bool):
    """Fallback: keeps a startup script in the Windows Startup folder."""
    try:
        app_data = os.environ.get("APPDATA")
        if not app_data:
            return
        startup_dir = Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if not startup_dir.exists():
            return
        
        shortcut_bat = startup_dir / "MyAcs_Background.bat"
        if enable:
            cmd = get_launch_command()
            with open(shortcut_bat, "w", encoding="utf-8") as f:
                f.write(f"@echo off\r\nstart \"\" {cmd}\r\nexit\r\n")
        else:
            if shortcut_bat.exists():
                shortcut_bat.unlink()
    except Exception as e:
        print(f"[Autostart] Startup folder sync error: {e}")


def install_scheduled_task() -> bool:
    """Creates a Windows Task Scheduler task that runs with highest privileges on logon."""
    try:
        cmd = get_launch_command()
        # Parse executable and arguments
        parts = cmd.split('"')
        tr = cmd
        task_cmd = f'schtasks /Create /TN "{APP_NAME}" /TR "{tr}" /SC ONLOGON /RL HIGHEST /F'
        result = subprocess.run(task_cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False
