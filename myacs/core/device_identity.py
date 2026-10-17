"""
MyAcs — Permanent Device Identity & Configuration Manager
Generates and maintains a permanent, unique hardware-tied Device ID
and persistent settings for the MyAcs Screen Mirroring application.
"""

import os
import sys
import json
import socket
import hashlib
import secrets
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import winreg
except ImportError:
    winreg = None


def get_app_data_dir() -> Path:
    """Return the persistent directory for MyAcs configuration."""
    # Prefer ProgramData so it is shared across all users and services, fallback to AppData
    program_data = os.environ.get("ProgramData")
    if program_data and os.path.exists(program_data):
        target = Path(program_data) / "MyAcs"
    else:
        app_data = os.environ.get("APPDATA") or os.path.expanduser("~")
        target = Path(app_data) / "MyAcs"
    
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fallback to local user directory
        target = Path.home() / ".myacs"
        target.mkdir(parents=True, exist_ok=True)
    
    return target


def get_permanent_hardware_id() -> str:
    """
    Query the permanent Windows MachineGuid or motherboard UUID.
    This remains identical across restarts, user logouts, and app reinstalls.
    """
    raw_guid = None

    # Method 1: Windows Registry MachineGuid (Universal on Windows 10/11)
    if winreg:
        for root_key in (winreg.HKEY_LOCAL_MACHINE,):
            for access_flag in (
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
                winreg.KEY_READ
            ):
                try:
                    with winreg.OpenKey(
                        root_key,
                        r"SOFTWARE\Microsoft\Cryptography",
                        0,
                        access_flag
                    ) as key:
                        val, _ = winreg.QueryValueEx(key, "MachineGuid")
                        if val and len(str(val).strip()) > 8:
                            raw_guid = str(val).strip()
                            break
                except Exception:
                    continue
            if raw_guid:
                break

    # Method 2: Fallback to persistent storage file if already generated
    config_file = get_app_data_dir() / "device.json"
    if not raw_guid and config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "device_id" in data and data["device_id"]:
                    return data["device_id"]
        except Exception:
            pass

    # Method 3: Machine name + node MAC address hash fallback
    if not raw_guid:
        import uuid
        raw_guid = f"{socket.gethostname()}-{uuid.getnode()}"

    # Generate permanent, clean formatted Device ID: ACS-XXXX-XXXX
    h = hashlib.sha256(raw_guid.encode("utf-8")).hexdigest().upper()
    device_id = f"ACS-{h[:4]}-{h[4:8]}"
    return device_id


class ConfigManager:
    """Manages persistent settings for MyAcs host and client."""
    
    def __init__(self):
        self.data_dir = get_app_data_dir()
        self.config_file = self.data_dir / "config.json"
        self.device_id = get_permanent_hardware_id()
        self.settings: Dict[str, Any] = self._load_default_settings()
        self.load()

    def _load_default_settings(self) -> Dict[str, Any]:
        hostname = socket.gethostname()
        # Generate a friendly random 6-digit PIN on first installation
        initial_pin = f"{secrets.randbelow(900000) + 100000}"
        return {
            "device_id": self.device_id,
            "device_name": hostname,
            "port": 45821,
            "discovery_port": 45820,
            "security_pin": initial_pin,
            "require_pin": True,
            "autostart": True,
            "quality": "balanced",  # balanced, high, ultra, speed
            "max_fps": 30,
            "scale": 1.0,           # 1.0 = native, 0.75 = 75%, 0.5 = 50%
            "allowed_viewers": [],  # Whitelisted device IDs
            "recent_connections": [], # List of recently connected remote IDs
        }

    def load(self):
        """Load configuration from disk, maintaining permanent device_id."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.settings.update(saved)
            except Exception as e:
                print(f"[ConfigManager] Error reading config: {e}")
        
        # Always enforce permanent device ID
        self.settings["device_id"] = self.device_id
        self.save()

    def save(self):
        """Save configuration atomically to disk."""
        try:
            temp_file = self.data_dir / "config.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
            temp_file.replace(self.config_file)
        except Exception as e:
            print(f"[ConfigManager] Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        self.settings[key] = value
        self.save()

    def set_security_pin(self, new_pin: str):
        self.settings["security_pin"] = str(new_pin).strip()
        self.save()

    def add_recent_connection(self, remote_id: str, remote_name: str = "", remote_ip: str = ""):
        recent = self.settings.get("recent_connections", [])
        # Remove if already exists
        recent = [r for r in recent if r.get("id") != remote_id]
        recent.insert(0, {
            "id": remote_id,
            "name": remote_name or remote_id,
            "ip": remote_ip
        })
        self.settings["recent_connections"] = recent[:10]
        self.save()


# Global singleton instance
config = ConfigManager()
