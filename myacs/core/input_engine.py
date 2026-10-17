"""
MyAcs — High-Performance Remote Input Engine
Handles low-latency mouse movement, hardware-level clicks, dragging, scrolling,
and keyboard input injection on Windows 10/11.
"""

import sys
import ctypes
import time
from typing import Optional, Dict, Any, List

from myacs.core.device_identity import config
from myacs.core.capture_engine import attach_to_active_input_desktop

# Disable PyAutoGUI artificial delays and failsafes for remote desktop control
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.0
except ImportError:
    pyautogui = None

# Windows API constants
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# JavaScript code -> Windows Virtual Key code mapping for special/navigation keys
VK_MAP = {
    "Backspace": 0x08,
    "Tab": 0x09,
    "Enter": 0x0D,
    "ShiftLeft": 0x10,
    "ShiftRight": 0x10,
    "ControlLeft": 0x11,
    "ControlRight": 0x11,
    "AltLeft": 0x12,
    "AltRight": 0x12,
    "Pause": 0x13,
    "CapsLock": 0x14,
    "Escape": 0x1B,
    "Space": 0x20,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "End": 0x23,
    "Home": 0x24,
    "ArrowLeft": 0x25,
    "ArrowUp": 0x26,
    "ArrowRight": 0x27,
    "ArrowDown": 0x28,
    "PrintScreen": 0x2C,
    "Insert": 0x2D,
    "Delete": 0x2E,
    "MetaLeft": 0x5B,
    "MetaRight": 0x5C,
    "ContextMenu": 0x5D,
    "NumLock": 0x90,
    "ScrollLock": 0x91,
    "F1": 0x70,
    "F2": 0x71,
    "F3": 0x72,
    "F4": 0x73,
    "F5": 0x74,
    "F6": 0x75,
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
}


class InputEngine:
    """Dispatches remote mouse and keyboard events directly to Windows interactive desktop."""

    def __init__(self):
        self.user32 = ctypes.windll.user32 if sys.platform.startswith("win") else None
        self._last_x: int = -1
        self._last_y: int = -1
        self._mon_left: int = 0
        self._mon_top: int = 0
        self._mon_width: int = 1920
        self._mon_height: int = 1080
        self._ensure_attached()

    def update_monitor_bounds(self, left: int, top: int, width: int, height: int):
        """Pre-cache active monitor bounds for instant nanosecond coordinate mapping."""
        self._mon_left = left
        self._mon_top = top
        self._mon_width = max(1, width)
        self._mon_height = max(1, height)

    def move_mouse_fast(self, x_ratio: float, y_ratio: float):
        """Ultra-low latency cursor positioning with pre-cached bounds in nanoseconds."""
        if not self.is_control_allowed() or not self.user32:
            return

        target_x = self._mon_left + int(x_ratio * self._mon_width)
        target_y = self._mon_top + int(y_ratio * self._mon_height)
        if target_x == self._last_x and target_y == self._last_y:
            return

        self._last_x = target_x
        self._last_y = target_y
        self.user32.SetCursorPos(target_x, target_y)

    def mouse_down_fast(self, button: str, x_ratio: float, y_ratio: float):
        """Instant mouse down injection with zero delay."""
        if not self.is_control_allowed() or not self.user32:
            return
        self.move_mouse_fast(x_ratio, y_ratio)
        btn = button.lower()
        if btn == "left" or btn == "0":
            self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        elif btn == "right" or btn == "2":
            self.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        elif btn == "middle" or btn == "1":
            self.user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)

    def mouse_up_fast(self, button: str, x_ratio: float, y_ratio: float):
        """Instant mouse up injection with zero delay."""
        if not self.is_control_allowed() or not self.user32:
            return
        self.move_mouse_fast(x_ratio, y_ratio)
        btn = button.lower()
        if btn == "left" or btn == "0":
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif btn == "right" or btn == "2":
            self.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        elif btn == "middle" or btn == "1":
            self.user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)

    def _ensure_attached(self):
        try:
            attach_to_active_input_desktop(force=False)
        except Exception:
            pass

    def is_control_allowed(self) -> bool:
        """Check if remote control is enabled in settings."""
        return config.get("allow_remote_control", True)

    def calculate_screen_coordinates(
        self,
        x_ratio: float,
        y_ratio: float,
        monitors: Optional[List[Dict[str, Any]]] = None,
        monitor_index: int = 1
    ) -> tuple[int, int]:
        """Maps normalized (0.0 - 1.0) client canvas coordinates to physical desktop pixel coordinates."""
        # Clamp ratios to valid 0.0 - 1.0 bounds
        x_ratio = max(0.0, min(1.0, float(x_ratio)))
        y_ratio = max(0.0, min(1.0, float(y_ratio)))

        if monitors:
            target_mon = next((m for m in monitors if m.get("index") == monitor_index), monitors[0])
            left = target_mon.get("left", 0)
            top = target_mon.get("top", 0)
            width = target_mon.get("width", 1920)
            height = target_mon.get("height", 1080)
            target_x = left + int(x_ratio * width)
            target_y = top + int(y_ratio * height)
            return target_x, target_y

        # Fallback to primary display metrics
        if self.user32:
            width = self.user32.GetSystemMetrics(0)
            height = self.user32.GetSystemMetrics(1)
            return int(x_ratio * width), int(y_ratio * height)

        return int(x_ratio * 1920), int(y_ratio * 1080)

    def move_mouse(
        self,
        x_ratio: float,
        y_ratio: float,
        monitors: Optional[List[Dict[str, Any]]] = None,
        monitor_index: int = 1
    ):
        """Move host cursor to specified coordinates (suppresses identical micro-moves to avoid cursor jitter)."""
        if not self.is_control_allowed() or not self.user32:
            return

        target_x, target_y = self.calculate_screen_coordinates(x_ratio, y_ratio, monitors, monitor_index)
        if target_x == self._last_x and target_y == self._last_y:
            return

        self._last_x = target_x
        self._last_y = target_y
        self.user32.SetCursorPos(target_x, target_y)

    def mouse_down(
        self,
        button: str = "left",
        x_ratio: Optional[float] = None,
        y_ratio: Optional[float] = None,
        monitors: Optional[List[Dict[str, Any]]] = None,
        monitor_index: int = 1
    ):
        """Press down a mouse button."""
        if not self.is_control_allowed() or not self.user32:
            return

        if x_ratio is not None and y_ratio is not None:
            self.move_mouse(x_ratio, y_ratio, monitors, monitor_index)

        btn = button.lower()
        if btn == "left" or btn == "0":
            self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        elif btn == "right" or btn == "2":
            self.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        elif btn == "middle" or btn == "1":
            self.user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)

    def mouse_up(
        self,
        button: str = "left",
        x_ratio: Optional[float] = None,
        y_ratio: Optional[float] = None,
        monitors: Optional[List[Dict[str, Any]]] = None,
        monitor_index: int = 1
    ):
        """Release a mouse button."""
        if not self.is_control_allowed() or not self.user32:
            return

        if x_ratio is not None and y_ratio is not None:
            self.move_mouse(x_ratio, y_ratio, monitors, monitor_index)

        btn = button.lower()
        if btn == "left" or btn == "0":
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif btn == "right" or btn == "2":
            self.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        elif btn == "middle" or btn == "1":
            self.user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)

    def mouse_click(
        self,
        button: str = "left",
        x_ratio: Optional[float] = None,
        y_ratio: Optional[float] = None,
        monitors: Optional[List[Dict[str, Any]]] = None,
        monitor_index: int = 1,
        clicks: int = 1
    ):
        """Execute a full mouse click or double-click."""
        for _ in range(clicks):
            self.mouse_down(button, x_ratio, y_ratio, monitors, monitor_index)
            time.sleep(0.01)
            self.mouse_up(button, x_ratio, y_ratio, monitors, monitor_index)
            if clicks > 1:
                time.sleep(0.05)

    def mouse_scroll(self, delta_x: float = 0.0, delta_y: float = 0.0):
        """Scroll the mouse wheel."""
        if not self.is_control_allowed() or not self.user32:
            return

        if delta_y != 0.0:
            # Invert browser scroll delta (positive browser deltaY is downward)
            wheel_delta = -int(delta_y)
            if abs(wheel_delta) < 40:
                wheel_delta = -120 if delta_y > 0 else 120
            self.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, wheel_delta, 0)

        if delta_x != 0.0:
            hwheel_delta = int(delta_x)
            self.user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, hwheel_delta, 0)

    def key_down(self, key: str, code: str = ""):
        """Inject key down event."""
        if not self.is_control_allowed():
            return

        # Check special navigation/modifier keys
        vk = VK_MAP.get(code) or VK_MAP.get(key)
        if vk and self.user32:
            self.user32.keybd_event(vk, 0, 0, 0)
            return

        # Use PyAutoGUI if available for named keys
        if pyautogui:
            py_key = key.lower()
            if py_key in pyautogui.KEY_NAMES:
                try:
                    pyautogui.keyDown(py_key)
                    return
                except Exception:
                    pass

        # Unicode character fallback via SendInput
        if len(key) == 1 and self.user32:
            self._send_unicode_char(key, is_up=False)

    def key_up(self, key: str, code: str = ""):
        """Inject key up event."""
        if not self.is_control_allowed():
            return

        vk = VK_MAP.get(code) or VK_MAP.get(key)
        if vk and self.user32:
            self.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            return

        if pyautogui:
            py_key = key.lower()
            if py_key in pyautogui.KEY_NAMES:
                try:
                    pyautogui.keyUp(py_key)
                    return
                except Exception:
                    pass

        if len(key) == 1 and self.user32:
            self._send_unicode_char(key, is_up=True)

    def _send_unicode_char(self, char: str, is_up: bool = False):
        """Send unicode character key event using SendInput."""
        try:
            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", ctypes.c_ushort),
                    ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
                ]

            class INPUT(ctypes.Structure):
                class _INPUT_UNION(ctypes.Union):
                    _fields_ = [("ki", KEYBDINPUT)]
                _fields_ = [
                    ("type", ctypes.c_ulong),
                    ("union", _INPUT_UNION)
                ]

            flags = KEYEVENTF_UNICODE
            if is_up:
                flags |= KEYEVENTF_KEYUP

            inp = INPUT()
            inp.type = 1  # INPUT_KEYBOARD
            inp.union.ki.wVk = 0
            inp.union.ki.wScan = ord(char)
            inp.union.ki.dwFlags = flags
            inp.union.ki.time = 0
            inp.union.ki.dwExtraInfo = None

            self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        except Exception:
            pass


# Singleton instance
input_engine = InputEngine()
