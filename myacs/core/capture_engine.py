"""
MyAcs — High-Performance Screen Capture Engine
Captures desktop screens with low latency on Windows 10/11,
supports one-time thread desktop attachment (zero mouse flickering),
multi-monitors, mouse cursor overlay rendering, and adaptive JPEG compression.

STRICT VIEW-ONLY GUARANTEE:
This module contains ZERO mouse/keyboard simulation or remote input execution.
"""

import time
import ctypes
import threading
from typing import Optional, Dict, Any, List, Tuple
import cv2
import numpy as np
import mss

# Suppress Windows GDI CAPTUREBLT flag (0x40000000).
# In Windows GDI, BitBlt with CAPTUREBLT forces the DWM / hardware mouse cursor
# to hide and restore on every frame blit, causing continuous, visible mouse cursor
# blinking/flickering on the host PC during screen capture.
# Disabling CAPTUREBLT (pure SRCCOPY) stops host cursor blinking completely,
# while _render_mouse_cursor() ensures the remote viewer sees the pointer cleanly.
try:
    import mss.windows.gdi
    mss.windows.gdi.CAPTUREBLT = 0
except Exception:
    pass

try:
    import win32gui
except ImportError:
    win32gui = None

_desktop_attached = False
_hdesk_handle = None


def sys_platform_is_windows() -> bool:
    import sys
    return sys.platform.startswith("win")


def attach_to_active_input_desktop(force: bool = False):
    """
    Ensure the current thread is attached to the active interactive input desktop ONCE.
    Keeping the handle open avoids desktop context switching and completely prevents
    hardware cursor blinking/flickering on the host PC.
    """
    global _desktop_attached, _hdesk_handle
    if not sys_platform_is_windows():
        return
    if _desktop_attached and not force:
        return

    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)  # GENERIC_ALL
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            _hdesk_handle = hdesk
            _desktop_attached = True
    except Exception:
        pass


class ScreenCaptureEngine:
    """Captures desktop frames, renders cursor overlay, and provides stream chunks."""

    QUALITY_PRESETS = {
        "speed": {"jpeg_quality": 60, "scale": 0.65, "max_fps": 60},
        "balanced": {"jpeg_quality": 75, "scale": 0.85, "max_fps": 60},
        "high": {"jpeg_quality": 85, "scale": 1.0, "max_fps": 60},
        "ultra": {"jpeg_quality": 92, "scale": 1.0, "max_fps": 60},
    }

    def __init__(self):
        self.sct: Optional[mss.MSS] = None
        self.selected_monitor_index = 1
        self.quality_mode = "balanced"
        self.custom_scale: Optional[float] = None
        self.custom_quality: Optional[int] = None
        
        # State tracking
        self.last_frame_bytes: Optional[bytes] = None
        self.frame_seq = 0
        self.current_fps = 0.0
        self._fps_counter = 0
        self._fps_last_calc = time.time()
        self.lock = threading.Lock()
        self._monitors_cache: Optional[List[Dict[str, Any]]] = None
        
        self._init_mss()

    def _init_mss(self):
        attach_to_active_input_desktop(force=True)
        try:
            if self.sct:
                self.sct.close()
        except Exception:
            pass
        self.sct = mss.MSS()
        self._monitors_cache = None

    def get_monitors(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """List all available physical and virtual displays (cached for low latency)."""
        if self._monitors_cache and not force_refresh:
            return self._monitors_cache
        with self.lock:
            try:
                monitors = []
                for i, mon in enumerate(self.sct.monitors):
                    if i == 0:
                        # Monitor 0 in MSS is the virtual full desktop covering all screens
                        continue
                    monitors.append({
                        "index": i,
                        "name": f"Display {i}",
                        "width": mon["width"],
                        "height": mon["height"],
                        "left": mon["left"],
                        "top": mon["top"],
                        "is_primary": (i == 1)
                    })
                self._monitors_cache = monitors
                return monitors
            except Exception:
                self._init_mss()
                return [{"index": 1, "name": "Primary Display", "width": 1920, "height": 1080}]

    def set_monitor(self, monitor_index: int):
        with self.lock:
            if 1 <= monitor_index < len(self.sct.monitors):
                self.selected_monitor_index = monitor_index

    def set_quality(self, mode: str, scale: Optional[float] = None, quality: Optional[int] = None):
        with self.lock:
            if mode in self.QUALITY_PRESETS:
                self.quality_mode = mode
            if scale is not None:
                self.custom_scale = max(0.25, min(1.0, scale))
            if quality is not None:
                self.custom_quality = max(20, min(100, quality))

    def get_max_fps(self) -> int:
        """Returns the target frame rate for current quality preset."""
        preset = self.QUALITY_PRESETS.get(self.quality_mode, self.QUALITY_PRESETS["balanced"])
        return preset.get("max_fps", 60)

    def get_selected_monitor_rect(self) -> Tuple[int, int, int, int]:
        """Returns (left, top, width, height) of currently selected monitor."""
        monitors = self.get_monitors()
        target = next((m for m in monitors if m.get("index") == self.selected_monitor_index), monitors[0] if monitors else {})
        return (
            target.get("left", 0),
            target.get("top", 0),
            target.get("width", 1920),
            target.get("height", 1080)
        )

    def _render_mouse_cursor(self, img_np: np.ndarray, monitor: dict):
        """
        Draws the host mouse pointer cleanly onto the captured frame.
        The host PC's hardware mouse does NOT blink, but remote viewers can see
        the cursor position clearly in real-time.
        """
        if not win32gui:
            return
        try:
            cur_x, cur_y = win32gui.GetCursorPos()
            rel_x = cur_x - monitor["left"]
            rel_y = cur_y - monitor["top"]

            # Only draw if cursor is within bounds of the captured monitor
            if 0 <= rel_x < monitor["width"] - 14 and 0 <= rel_y < monitor["height"] - 24:
                # Classic Windows arrow pointer polygon
                pts = np.array([
                    [rel_x, rel_y],
                    [rel_x, rel_y + 19],
                    [rel_x + 5, rel_y + 14],
                    [rel_x + 10, rel_y + 24],
                    [rel_x + 13, rel_y + 22],
                    [rel_x + 8, rel_y + 13],
                    [rel_x + 14, rel_y + 13]
                ], np.int32)

                # Fill white body and black border
                cv2.fillPoly(img_np, [pts], (255, 255, 255, 255))
                cv2.polylines(img_np, [pts], True, (0, 0, 0, 255), 2, cv2.LINE_AA)
        except Exception:
            pass

    def capture_frame(self, force: bool = False) -> Optional[Tuple[bytes, int, int, int]]:
        """
        Grabs a frame, renders mouse cursor, scales & compresses it to JPEG.
        Returns: (jpeg_bytes, width, height, sequence_number) or None if error.
        """
        with self.lock:
            try:
                mon_idx = self.selected_monitor_index
                if mon_idx >= len(self.sct.monitors):
                    mon_idx = 1
                monitor = self.sct.monitors[mon_idx]

                # Grab raw BGRA frame
                sct_img = self.sct.grab(monitor)
            except Exception as e:
                # Re-initialize only on desktop context change (e.g. UAC / lock)
                self._init_mss()
                try:
                    monitor = self.sct.monitors[1]
                    sct_img = self.sct.grab(monitor)
                except Exception:
                    return None

            raw_w, raw_h = sct_img.size
            img_np = np.array(sct_img, dtype=np.uint8)

            # Draw mouse pointer on the frame so remote viewers see it clearly
            self._render_mouse_cursor(img_np, monitor)

            # Determine encoding parameters
            preset = self.QUALITY_PRESETS.get(self.quality_mode, self.QUALITY_PRESETS["balanced"])
            scale = self.custom_scale if self.custom_scale is not None else preset["scale"]
            jpeg_quality = self.custom_quality if self.custom_quality is not None else preset["jpeg_quality"]

            # Resize if scale != 1.0
            if scale < 0.99:
                target_w = max(320, int(raw_w * scale))
                target_h = max(240, int(raw_h * scale))
                img_resized = cv2.resize(img_np, (target_w, target_h), interpolation=cv2.INTER_AREA)
            else:
                target_w, target_h = raw_w, raw_h
                img_resized = img_np

            # Convert BGRA to BGR for JPEG encoding
            if img_resized.shape[2] == 4:
                img_bgr = cv2.cvtColor(img_resized, cv2.COLOR_BGRA2BGR)
            else:
                img_bgr = img_resized

            # High-speed JPEG encoding with OpenCV
            encode_params = [
                cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality),
                cv2.IMWRITE_JPEG_OPTIMIZE, 0
            ]
            success, encoded_buf = cv2.imencode('.jpg', img_bgr, encode_params)
            if not success:
                return None

            frame_bytes = encoded_buf.tobytes()
            self.frame_seq += 1

            # Update FPS tracking
            self._fps_counter += 1
            now = time.time()
            if now - self._fps_last_calc >= 1.0:
                self.current_fps = round(self._fps_counter / (now - self._fps_last_calc), 1)
                self._fps_counter = 0
                self._fps_last_calc = now

            self.last_frame_bytes = frame_bytes
            return frame_bytes, target_w, target_h, self.frame_seq

    def close(self):
        with self.lock:
            if self.sct:
                try:
                    self.sct.close()
                except Exception:
                    pass
                self.sct = None
