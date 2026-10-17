"""
MyAcs — High-Performance Streaming Server & REST API
Provides WebSocket screen streaming, authentication, session lifecycle,
and REST endpoints for local device status and peer discovery.

STRICT VIEW-ONLY POLICY:
Any input control requests (mouse, keyboard, clipboard, file) are strictly blocked.
"""

import os
import sys
import time
import json
import socket
import struct
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from myacs.core.device_identity import config
from myacs.core.capture_engine import ScreenCaptureEngine
from myacs.core.security import session_manager
from myacs.core.discovery import lan_discovery, get_all_lan_ips
from myacs.core.input_engine import input_engine

# Initialize FastAPI application
app = FastAPI(title="MyAcs Screen Mirroring", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global capture engine
capture_engine = ScreenCaptureEngine()

# Path to static frontend assets
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
STATIC_DIR = UI_DIR / "static"


# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    """Returns host status, identity, and network addresses."""
    active_sessions = session_manager.get_active_sessions_summary()
    return {
        "device_id": config.get("device_id"),
        "device_name": config.get("device_name"),
        "port": config.get("port", 45821),
        "security_pin": config.get("security_pin"),
        "require_pin": config.get("require_pin", True),
        "autostart": config.get("autostart", True),
        "allow_remote_control": config.get("allow_remote_control", True),
        "quality": capture_engine.quality_mode,
        "current_fps": capture_engine.current_fps,
        "monitors": capture_engine.get_monitors(),
        "selected_monitor": capture_engine.selected_monitor_index,
        "lan_ips": get_all_lan_ips(),
        "active_viewers_count": len(active_sessions),
        "active_viewers": active_sessions,
        "recent_connections": config.get("recent_connections", [])
    }


@app.get("/api/peers")
async def get_peers():
    """Returns list of online MyAcs devices discovered on the LAN."""
    peers = lan_discovery.get_online_peers()
    return {"peers": peers}


@app.post("/api/peers/probe")
async def probe_peer(request: Request):
    """Actively probes for a specific device ID over UDP on the local network."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    target_id = body.get("target_id", "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="Missing target_id")

    peer = lan_discovery.probe_device(target_id, timeout_sec=2.0)
    if peer:
        return {"found": True, "peer": peer}
    return {"found": False, "message": f"Device {target_id} not found on local network."}


@app.get("/api/settings")
async def get_settings():
    return {
        "device_id": config.get("device_id"),
        "device_name": config.get("device_name"),
        "security_pin": config.get("security_pin"),
        "require_pin": config.get("require_pin", True),
        "autostart": config.get("autostart", True),
        "quality": config.get("quality", "balanced"),
        "allowed_viewers": config.get("allowed_viewers", [])
    }


@app.post("/api/settings")
async def update_settings(request: Request):
    body = await request.json()
    if "security_pin" in body:
        new_pin = str(body["security_pin"]).strip()
        if len(new_pin) >= 4:
            config.set_security_pin(new_pin)

    if "device_name" in body and body["device_name"].strip():
        config.set("device_name", body["device_name"].strip())

    if "require_pin" in body:
        config.set("require_pin", bool(body["require_pin"]))

    if "quality" in body and body["quality"] in capture_engine.QUALITY_PRESETS:
        config.set("quality", body["quality"])
        capture_engine.set_quality(body["quality"])

    if "autostart" in body:
        config.set("autostart", bool(body["autostart"]))
        # Update Windows autostart configuration
        from myacs.service.autostart import set_windows_autostart
        set_windows_autostart(bool(body["autostart"]))

    return {"success": True, "message": "Settings updated."}


@app.post("/api/sessions/disconnect")
async def disconnect_session(request: Request):
    body = await request.json()
    token = body.get("token")
    if token:
        session_manager.close_session(token)
        return {"success": True, "message": "Viewer disconnected."}
    return {"success": False, "message": "Token missing."}


# -------------------------------------------------------------
# WebSocket Screen Streaming Endpoint
# -------------------------------------------------------------

@app.websocket("/ws/stream")
async def websocket_stream_endpoint(websocket: WebSocket):
    """
    Main real-time screen streaming WebSocket connection.
    Authenticates viewer, transmits JPEG frames, and tracks bandwidth/latency.
    """
    await websocket.accept()
    client_ip = websocket.client.host if websocket.client else "127.0.0.1"
    session_token = None
    authenticated = False
    
    # Per-connection capture preferences (60 FPS high-refresh rate)
    desired_fps = capture_engine.get_max_fps()
    sleep_interval = 1.0 / desired_fps
    client_ack_pending = False

    # Disable Nagle's algorithm (TCP_NODELAY) for instant packet flush
    try:
        transport = websocket.scope.get("transport")
        if transport:
            sock = transport.get_extra_info("socket")
            if sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    
    try:
        # Step 1: Authentication Handshake
        init_data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        auth_msg = json.loads(init_data)

        if auth_msg.get("type") != "auth":
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Protocol error: expected auth message."
            }))
            await websocket.close()
            return

        pin = auth_msg.get("pin", "")
        viewer_id = auth_msg.get("viewer_device_id", "")
        viewer_name = auth_msg.get("viewer_name", "Viewer PC")

        success, msg, token = session_manager.authenticate(
            provided_pin=pin,
            viewer_device_id=viewer_id,
            viewer_name=viewer_name,
            client_ip=client_ip
        )

        if not success:
            await websocket.send_text(json.dumps({
                "type": "auth_error",
                "message": msg
            }))
            await websocket.close()
            return

        session_token = token
        authenticated = True

        # Pre-cache monitor bounds on input engine for instant nanosecond coordinate mapping
        rect = capture_engine.get_selected_monitor_rect()
        input_engine.update_monitor_bounds(*rect)

        # Send authentication success response with device information
        allow_ctrl = config.get("allow_remote_control", True)
        await websocket.send_text(json.dumps({
            "type": "auth_success",
            "session_token": session_token,
            "host_device_id": config.get("device_id"),
            "host_name": config.get("device_name"),
            "monitors": capture_engine.get_monitors(),
            "selected_monitor": capture_engine.selected_monitor_index,
            "quality": capture_engine.quality_mode,
            "allow_control": allow_ctrl,
            "view_only": not allow_ctrl
        }))

        # Background task to receive client control commands & remote input
        async def client_listener():
            nonlocal client_ack_pending, desired_fps, sleep_interval
            while True:
                try:
                    message = await websocket.receive()
                    msg_type = message.get("type")

                    if msg_type == "websocket.disconnect":
                        break

                    # 1. High-Performance Binary Protocol (Direct binary mouse events)
                    if "bytes" in message:
                        raw = message["bytes"]
                        if not raw:
                            continue
                        op = raw[0]
                        if op == 1 and len(raw) >= 5:  # mouse_move (5 bytes: [1, x_hi, x_lo, y_hi, y_lo])
                            x_norm = ((raw[1] << 8) | raw[2]) / 65535.0
                            y_norm = ((raw[3] << 8) | raw[4]) / 65535.0
                            input_engine.move_mouse_fast(x_norm, y_norm)
                        elif op == 2 and len(raw) >= 6:  # mouse_down (6 bytes)
                            btn_code = raw[1]
                            btn = "right" if btn_code == 2 else ("middle" if btn_code == 1 else "left")
                            x_norm = ((raw[2] << 8) | raw[3]) / 65535.0
                            y_norm = ((raw[4] << 8) | raw[5]) / 65535.0
                            input_engine.mouse_down_fast(btn, x_norm, y_norm)
                        elif op == 3 and len(raw) >= 6:  # mouse_up (6 bytes)
                            btn_code = raw[1]
                            btn = "right" if btn_code == 2 else ("middle" if btn_code == 1 else "left")
                            x_norm = ((raw[2] << 8) | raw[3]) / 65535.0
                            y_norm = ((raw[4] << 8) | raw[5]) / 65535.0
                            input_engine.mouse_up_fast(btn, x_norm, y_norm)
                        elif op == 4 and len(raw) >= 5:  # mouse_scroll (5 bytes)
                            delta_x, delta_y = struct.unpack_from("!hh", raw, 1)
                            input_engine.mouse_scroll(delta_x, delta_y)

                    # 2. Text / JSON Protocol (Commands, keyboard, fallbacks)
                    elif "text" in message:
                        msg = json.loads(message["text"])
                        t = msg.get("type")

                        if t == "ack":
                            client_ack_pending = False

                        elif t == "set_quality":
                            mode = msg.get("mode")
                            if mode in capture_engine.QUALITY_PRESETS:
                                capture_engine.set_quality(mode)
                                desired_fps = capture_engine.get_max_fps()

                        elif t == "set_monitor":
                            idx = int(msg.get("index", 1))
                            capture_engine.set_monitor(idx)
                            input_engine.update_monitor_bounds(*capture_engine.get_selected_monitor_rect())

                        elif t == "mouse_move":
                            x_ratio = float(msg.get("x", 0.0))
                            y_ratio = float(msg.get("y", 0.0))
                            input_engine.move_mouse_fast(x_ratio, y_ratio)

                        elif t == "mouse_down":
                            button = msg.get("button", "left")
                            x_ratio = float(msg.get("x", 0.0)) if msg.get("x") is not None else 0.0
                            y_ratio = float(msg.get("y", 0.0)) if msg.get("y") is not None else 0.0
                            input_engine.mouse_down_fast(button, x_ratio, y_ratio)

                        elif t == "mouse_up":
                            button = msg.get("button", "left")
                            x_ratio = float(msg.get("x", 0.0)) if msg.get("x") is not None else 0.0
                            y_ratio = float(msg.get("y", 0.0)) if msg.get("y") is not None else 0.0
                            input_engine.mouse_up_fast(button, x_ratio, y_ratio)

                        elif t == "mouse_click":
                            button = msg.get("button", "left")
                            x_ratio = msg.get("x")
                            y_ratio = msg.get("y")
                            clicks = int(msg.get("clicks", 1))
                            monitors = capture_engine.get_monitors()
                            input_engine.mouse_click(button, x_ratio, y_ratio, monitors, capture_engine.selected_monitor_index, clicks)

                        elif t == "mouse_scroll":
                            delta_x = float(msg.get("delta_x", 0.0))
                            delta_y = float(msg.get("delta_y", 0.0))
                            input_engine.mouse_scroll(delta_x, delta_y)

                        elif t == "key_down":
                            key = msg.get("key", "")
                            code = msg.get("code", "")
                            input_engine.key_down(key, code)

                        elif t == "key_up":
                            key = msg.get("key", "")
                            code = msg.get("code", "")
                            input_engine.key_up(key, code)

                except Exception:
                    break

        listener_task = asyncio.create_task(client_listener())

        # Step 2: High-Performance Screen Streaming Loop (60 FPS silky smooth)
        session = session_manager.validate_session(session_token)

        while authenticated:
            loop_start = time.time()
            target_frame_time = 1.0 / desired_fps

            # Capture desktop frame
            capture_res = capture_engine.capture_frame()
            if capture_res is not None:
                frame_bytes, width, height, seq = capture_res

                # Build frame header
                allow_ctrl = config.get("allow_remote_control", True)
                header = {
                    "type": "frame_header",
                    "seq": seq,
                    "width": width,
                    "height": height,
                    "timestamp": time.time(),
                    "fps": capture_engine.current_fps,
                    "allow_control": allow_ctrl,
                    "view_only": not allow_ctrl
                }

                # Send header followed by binary JPEG payload
                await websocket.send_text(json.dumps(header))
                await websocket.send_bytes(frame_bytes)

                if session:
                    session["frames_sent"] += 1
                    session["bytes_sent"] += len(frame_bytes)

            # Frame rate pacing (ultra-precise minimal sleep)
            elapsed = time.time() - loop_start
            sleep_needed = max(0.001, target_frame_time - elapsed)
            await asyncio.sleep(sleep_needed)

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[StreamingServer] WebSocket error from {client_ip}: {e}")
    finally:
        if session_token:
            session_manager.close_session(session_token)
        try:
            await websocket.close()
        except Exception:
            pass


# -------------------------------------------------------------
# Static HTML UI Route
# -------------------------------------------------------------

@app.get("/")
@app.get("/view")
async def index_page():
    index_html = UI_DIR / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return HTMLResponse("<h1>MyAcs Screen Mirroring</h1><p>UI loading...</p>")

# Mount static folder if it exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def run_server(host: str = "0.0.0.0", port: int = 45821):
    """Starts the Uvicorn streaming server synchronously."""
    # Ensure stdout/stderr are valid streams so logging never crashes under pythonw.exe
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

    try:
        server_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_config=None,
            access_log=False
        )
        server = uvicorn.Server(server_config)
        server.run()
    except Exception as e:
        uvicorn.run(app, host=host, port=port, log_level="warning")
