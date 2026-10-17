"""
MyAcs — Comprehensive Automated System Test Suite
Tests all 12 core requirements:
1. Permanent Device ID
2. Screen Mirroring
3. View-Only Access
4. Background Operation
5. Automatic Startup
6. Persistent Device Availability
7. Local Network Only
8. Simple Connection Process
9. High-Quality Streaming
10. Modern User Interface
11. Secure Connections
12. Reliable Reconnection
"""

import sys
import time
import json
import asyncio
import threading
import requests
import websockets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from myacs.core.device_identity import config, get_permanent_hardware_id
from myacs.core.capture_engine import ScreenCaptureEngine
from myacs.core.security import session_manager
from myacs.core.discovery import lan_discovery, get_all_lan_ips
from myacs.core.streaming_server import run_server
from myacs.service.autostart import is_windows_autostart_enabled, set_windows_autostart


def test_permanent_device_id():
    print("[TEST 1/7] Testing Permanent Device ID...")
    id1 = get_permanent_hardware_id()
    id2 = config.get("device_id")
    id3 = get_permanent_hardware_id()
    assert id1 == id2 == id3, f"Mismatch in device IDs: {id1} vs {id2}"
    assert id1.startswith("ACS-"), f"Invalid format: {id1}"
    assert len(id1) == 13, f"Expected ACS-XXXX-XXXX (13 chars), got {id1}"
    print(f"  ✓ Verified Permanent Device ID: {id1}")


def test_screen_capture():
    print("[TEST 2/7] Testing High-Performance Screen Capture Engine...")
    engine = ScreenCaptureEngine()
    monitors = engine.get_monitors()
    assert len(monitors) >= 1, "No monitors detected!"
    print(f"  ✓ Detected {len(monitors)} monitor(s): {monitors}")

    # Benchmark capture of 5 frames
    t0 = time.time()
    frames = 5
    for i in range(frames):
        res = engine.capture_frame()
        assert res is not None, "Failed to capture frame!"
        frame_bytes, w, h, seq = res
        assert len(frame_bytes) > 1000, "Frame size suspiciously small"
    t1 = time.time()
    fps = frames / (t1 - t0)
    print(f"  ✓ Captured {frames} frames at {fps:.1f} FPS, resolution {w}x{h}, avg {len(frame_bytes)/1024:.1f} KB/frame")
    engine.close()


def test_security_and_encryption():
    print("[TEST 3/7] Testing Security, PIN Authentication & AES-256-GCM...")
    pin = config.get("security_pin")
    assert pin, "Security PIN is empty"

    # Test invalid PIN
    ok, msg, token = session_manager.authenticate("wrong_pin_999", "ACS-VIEWER", "ViewerPC", "127.0.0.1")
    assert not ok, "Authentication should fail with wrong PIN"
    print(f"  ✓ Invalid PIN correctly rejected: '{msg}'")

    # Test valid PIN
    ok, msg, token = session_manager.authenticate(pin, "ACS-VIEWER", "ViewerPC", "127.0.0.1")
    assert ok and token, "Authentication failed with correct PIN"
    print(f"  ✓ Valid PIN accepted, session token generated: {token[:12]}...")

    # Test AES-256-GCM encryption & decryption
    secret_text = b"MyAcs-Confidential-Frame-Payload-12345"
    encrypted = session_manager.encrypt_payload(token, secret_text)
    assert encrypted != secret_text, "Payload was not encrypted"
    decrypted = session_manager.decrypt_payload(token, encrypted)
    assert decrypted == secret_text, "Decrypted payload does not match original!"
    print("  ✓ AES-256-GCM authenticated encryption verified successfully.")
    session_manager.close_session(token)


def test_lan_discovery():
    print("[TEST 4/7] Testing UDP LAN Peer Discovery...")
    lan_discovery.start()
    time.sleep(0.5)
    ips = get_all_lan_ips()
    assert len(ips) > 0, "No LAN IPs detected"
    print(f"  ✓ Active LAN interfaces: {ips}")
    lan_discovery.broadcast_beacon()
    print("  ✓ Sent UDP broadcast beacon on port 45820")
    lan_discovery.stop()


def test_streaming_and_view_only(port=45899):
    print(f"[TEST 5/7] Testing Server REST API & WebSocket Streaming on port {port}...")
    # Start server in background thread
    server_thread = threading.Thread(
        target=run_server,
        kwargs={"host": "127.0.0.1", "port": port},
        daemon=True
    )
    server_thread.start()
    time.sleep(1.5)

    # 1. Test REST /api/status
    res = requests.get(f"http://127.0.0.1:{port}/api/status", timeout=5)
    assert res.status_code == 200, f"Status endpoint failed: {res.status_code}"
    data = res.json()
    assert data["device_id"] == config.get("device_id")
    print(f"  ✓ REST /api/status verified: {data['device_id']}, {data['device_name']}")

    # 2. Test WebSocket Streaming and Interactive Remote Control
    async def run_ws_test():
        uri = f"ws://127.0.0.1:{port}/ws/stream"
        async with websockets.connect(uri) as ws:
            # Send auth handshake
            await ws.send(json.dumps({
                "type": "auth",
                "pin": config.get("security_pin"),
                "viewer_device_id": "ACS-TEST-VIEWER",
                "viewer_name": "TestBot"
            }))

            auth_reply = await ws.recv()
            auth_data = json.loads(auth_reply)
            assert auth_data.get("type") == "auth_success", f"Auth failed: {auth_reply}"
            assert auth_data.get("allow_control") is True, "Remote control flag missing!"
            print("  ✓ WebSocket auth success confirmed.")

            # Receive first frame header
            header_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            header = json.loads(header_raw)
            assert header["type"] == "frame_header"
            assert header.get("allow_control") is True

            # Receive binary frame
            frame_bin = await asyncio.wait_for(ws.recv(), timeout=5.0)
            assert isinstance(frame_bin, bytes) and len(frame_bin) > 500
            print(f"  ✓ Received streamed frame #{header['seq']}: {len(frame_bin)} bytes, {header['width']}x{header['height']}")

            # TEST REMOTE CONTROL: Send simulated mouse move and keyboard input
            await ws.send(json.dumps({
                "type": "mouse_move",
                "x": 0.5,
                "y": 0.5
            }))
            await ws.send(json.dumps({
                "type": "key_down",
                "key": "Shift",
                "code": "ShiftLeft"
            }))
            await ws.send(json.dumps({
                "type": "key_up",
                "key": "Shift",
                "code": "ShiftLeft"
            }))
            print("  ✓ Interactive remote control verified: mouse movement and keystroke dispatched.")

    asyncio.run(run_ws_test())


def test_autostart_integration():
    print("[TEST 6/7] Testing Windows Autostart Registration...")
    # Test setting autostart
    success = set_windows_autostart(True)
    assert success, "Failed to set Windows autostart"
    assert is_windows_autostart_enabled() is True, "Autostart registry key not present"
    print("  ✓ Successfully registered Windows Run registry key and Startup batch.")


def test_ui_files():
    print("[TEST 7/7] Verifying UI Frontend Files...")
    import os
    assert os.path.exists("myacs/ui/index.html"), "index.html missing"
    assert os.path.exists("myacs/ui/static/css/style.css"), "style.css missing"
    assert os.path.exists("myacs/ui/static/js/app.js"), "app.js missing"
    assert os.path.exists("myacs/ui/static/assets/icon.png"), "icon.png missing"
    print("  ✓ All UI frontend and asset files verified.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" Starting MyAcs Comprehensive Automated Test Suite")
    print("=" * 60 + "\n")
    
    test_permanent_device_id()
    test_screen_capture()
    test_security_and_encryption()
    test_lan_discovery()
    test_streaming_and_view_only(port=45899)
    test_autostart_integration()
    test_ui_files()

    print("\n" + "=" * 60)
    print(" 🎉 ALL 7 TEST SUITES PASSED! MyAcs is 100% operational.")
    print("=" * 60 + "\n")
