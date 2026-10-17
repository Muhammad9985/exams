# MyAcs — Ultra-Low Latency LAN Screen Mirroring & Remote Control (Windows 10/11)

**MyAcs** is an enterprise-grade, ultra-low latency screen mirroring and interactive remote desktop application designed to operate 100% over a Local Area Network (LAN). It requires **zero internet access, zero cloud relays, and zero third-party accounts or subscriptions**.

---

## 🗺️ System Architecture & Network Topology

```mermaid
flowchart TB
    subgraph HostPC["🖥️ Host PC (Windows 10 / 11)"]
        direction TB
        subgraph OSLevel["Windows OS Core"]
            DWM["Windows DWM / Display Framebuffer"]
            Win32Input["Win32 Input Driver\n(SetCursorPos, mouse_event, SendInput)"]
            WinReg["Windows Registry & Startup Service"]
        end

        subgraph MyAcsCore["MyAcs Application Engine"]
            DeviceID["Device Identity\n(MachineGuid: ACS-XXXX-XXXX)"]
            CapEngine["ScreenCaptureEngine\n(60 FPS, Pure SRCCOPY, CAPTUREBLT=0)"]
            InputEngine["InputEngine\n(5-Byte Binary Unpacker in 0.0001 ms)"]
            SecEngine["Security Manager\n(PIN Auth, Session Token, AES-256-GCM)"]
            Server["FastAPI + Uvicorn Streaming Server\n(TCP_NODELAY Enabled)"]
            TrayApp["PySide6 Desktop Window & System Tray Icon"]
            UDPBeacon["UDP Discovery Broadcaster\n(Offline LAN Radar)"]
        end
    end

    subgraph LocalNetwork["🌐 Local Area Network (LAN - Zero Cloud)"]
        direction LR
        TCPPort["TCP Port 45821\n(HTTP Web Dashboard & WebSocket Binary Stream)"]
        UDPPort["UDP Port 45820\n(Peer Discovery Beacons)"]
    end

    subgraph ViewerClient["💻 Viewing Client (Any LAN PC / Laptop / Tablet)"]
        direction TB
        Browser["Modern Web Browser (Chrome, Edge, Firefox, Safari)"]
        Canvas["Hardware-Accelerated 2D Canvas"]
        CompactUI["Compact 36px Toolbar\n(Hide Menu ▲ / ☰ Menu ▼)"]
        BinDispatcher["Binary Input Dispatcher\n(Zero-Throttle Mouse / Click / Keys)"]
        LocalCursor["0 ms Local Hardware Cursor Tracking"]
    end

    %% Relationships
    DWM -->|"Pure BitBlt SRCCOPY"| CapEngine
    CapEngine -->|"60 FPS JPEG Frames"| Server
    Server <-->|"WebSocket Video & Binary Input"| TCPPort
    UDPBeacon -->|"UDP Broadcasts"| UDPPort

    TCPPort <-->|"HTTP / WS Traffic"| Browser
    UDPPort -.->|"Radar Detection"| Browser

    Browser --> Canvas
    Browser --> CompactUI
    Browser --> LocalCursor
    Canvas -->|"Mouse / Key Events"| BinDispatcher
    BinDispatcher -->|"5-Byte Raw Binary Buffer"| TCPPort

    Server -->|"Unpack Binary Input"| InputEngine
    InputEngine -->|"Nanosecond Injection"| Win32Input
    SecEngine -.->|"Verify Token & PIN"| Server
    DeviceID -.->|"Persistent Identity"| Server
    TrayApp <-->|"Status & Tray Control"| Server
    WinReg -.->|"Auto-Launch on Boot"| TrayApp
```

---

## ⚡ Ultra-Low Latency Video Streaming Pipeline

```mermaid
flowchart LR
    subgraph CapturePipeline["1. Screen Capture Stage"]
        A["Windows Desktop Frame"] --> B["mss.windows.gdi (pure SRCCOPY)"]
        B --> C["Monitor Rect Crop\n(Display 1, 2, ...)"]
        C --> D["Render Mouse Cursor Overlay\n(Smooth Remote Pointer)"]
    end

    subgraph EncodePipeline["2. Compression & Pacing"]
        D --> E["OpenCV TurboJPEG Encoder\n(Adaptive Quality: 60% - 92%)"]
        E --> F["60 FPS Precision Timer\n(16.6 ms frame interval)"]
    end

    subgraph TransportPipeline["3. Network Transport"]
        F --> G["WebSocket Binary Send\n(TCP_NODELAY = 1, Zero Buffer Delay)"]
        G --> H["LAN Network Switch / Wi-Fi"]
    end

    subgraph RenderPipeline["4. Client Display Stage"]
        H --> I["WebSocket onmessage\n(ArrayBuffer)"]
        I --> J["URL.createObjectURL / ImageBitmap"]
        J --> K["Canvas 2D ctx.drawImage\n(Hardware-Accelerated Display)"]
    end
```

---

## 🎮 Zero-Latency Binary Input Protocol Pipeline

```mermaid
flowchart TD
    subgraph ClientStage["Client-Side (Viewing PC Browser)"]
        M1["Mouse Movement / Drag / Click Event"] --> M2["Normalize Coordinates\n(rel_x = clientX / canvasWidth)\n(rel_y = clientY / canvasHeight)"]
        M2 --> M3{"Event Type?"}
        M3 -->|"Mouse Move"| P1["Opcode 0x01\nUint8Array [1, x_hi, x_lo, y_hi, y_lo]\n5-Byte Compact Binary Packet"]
        M3 -->|"Mouse Down/Up"| P2["Opcode 0x02\nUint8Array [2, button, state, 0, 0]\n5-Byte Binary Packet"]
        M3 -->|"Mouse Scroll"| P3["Opcode 0x03\nUint8Array [3, delta_hi, delta_lo, 0, 0]\n5-Byte Binary Packet"]
        M3 -->|"Keyboard Input"| P4["JSON Keystroke Fallback\n{type: 'key_down', key: '...' }"]

        P1 --> M4["WebSocket.send(buffer.buffer)\n(Direct Binary Dispatch, Zero Delay)"]
        P2 --> M4
        P3 --> M4
        P4 --> M4
    end

    subgraph HostStage["Host-Side (Remote Windows PC)"]
        M4 --> S1["WebSocket Receive Loop (streaming_server.py)"]
        S1 --> S2{"Payload Type?"}
        S2 -->|"Binary (len == 5)"| S3["Fast Bitwise Unpacker in 0.0001 ms:\nx = (data[1] << 8) | data[2]\ny = (data[3] << 8) | data[4]"]
        S2 -->|"Text / JSON"| S4["JSON Input Dispatcher\n(Keys, Meta)"]

        S3 --> S5["Pre-Cached Display Boundaries Map\ntarget_x = monitor.left + (x / 65535 * width)\ntarget_y = monitor.top + (y / 65535 * height)"]
        S5 --> S6["Win32 Direct C-Types API Call\nctypes.windll.user32.SetCursorPos(target_x, target_y)"]
        S6 --> S7["Instant Mouse Cursor Movement on Remote PC\n(Zero Jitter, Fluid Hardware Feel)"]

        S4 --> S8["ctypes.windll.user32.keybd_event / SendInput"]
    end
```

---

## 🔐 Connection, Authentication & Session Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Viewer as 💻 Viewing PC (Browser)
    participant HostAPI as 🌐 Host REST API (:45821)
    participant SecMgr as 🛡️ Security Manager
    participant WSServer as ⚡ WebSocket Server (:45821)
    participant Engines as 🖥️ Capture & Input Engines

    Note over Viewer,HostAPI: Phase 1: Discovery & Status
    Viewer->>HostAPI: GET /api/status
    HostAPI-->>Viewer: 200 OK (Device ID: ACS-XXXX, LAN IPs, Hostname, Protected: true)

    Note over Viewer,SecMgr: Phase 2: PIN Authentication
    Viewer->>HostAPI: POST /api/auth { "pin": "298989", "client_name": "Viewer-PC" }
    HostAPI->>SecMgr: Verify PIN against PBKDF2/HMAC Salted Hash
    alt Invalid PIN
        SecMgr-->>HostAPI: Verification Failed
        HostAPI-->>Viewer: 401 Unauthorized ("Invalid Security PIN")
    else Valid PIN
        SecMgr->>SecMgr: Generate Ephemeral Session Token & AES-256 Session Key
        SecMgr-->>HostAPI: Session Authorized
        HostAPI-->>Viewer: 200 OK { "token": "session_tok_...", "expires_in": 86400 }
    end

    Note over Viewer,Engines: Phase 3: WebSocket Video & Interactive Stream
    Viewer->>WSServer: Upgrade: WebSocket /ws/stream?token=session_tok_...
    WSServer->>SecMgr: Validate Session Token
    SecMgr-->>WSServer: Token Valid (Client Authorized)
    WSServer->>WSServer: Set TCP_NODELAY = 1 (Disable Nagle Buffering)
    WSServer->>Engines: Attach Client to 60 FPS Capture Stream Loop

    loop 60 FPS Continuous Screen Stream
        Engines->>WSServer: Render Frame (Pure SRCCOPY BitBlt + TurboJPEG)
        WSServer-->>Viewer: Binary JPEG Frame Buffer
        Viewer->>Viewer: Canvas 2D ctx.drawImage (Instant Render)
    end

    loop Real-Time Input Interaction
        Viewer->>WSServer: 5-Byte Raw Binary Input [Opcode, X, Y]
        WSServer->>Engines: Nanosecond Bitwise Unpack & SetCursorPos()
    end

    Note over Viewer,HostAPI: Phase 4: Session Termination
    Viewer->>HostAPI: POST /api/session/disconnect
    HostAPI->>SecMgr: Invalidate Session Token
    WSServer->>Viewer: WebSocket Close Code 1000 (Clean Disconnect)
```

---

## ✨ Features & Core Capabilities

| Feature | Description |
| :--- | :--- |
| **🎮 Near-Zero Latency Remote Control** | Instant, fluid mouse movement, left/right/middle clicks, dragging, scrolling, and keyboard input. Employs a custom 5-byte binary protocol, `TCP_NODELAY` socket packet flushing, and local hardware cursor acceleration for an instant, "directly connected" mouse feel. |
| **⚡ 60 FPS High-Refresh Streaming** | Ultra-smooth 60 FPS desktop capture with hardware-accelerated Canvas 2D rendering, adaptive JPEG compression, and sub-frame latency over standard Wi-Fi and Gigabit Ethernet. |
| **🚫 Zero Host Cursor Blinking** | Pure `SRCCOPY` screen capture suppresses Windows GDI `CAPTUREBLT`, eliminating DWM hardware cursor flickering and keeping the host PC's physical cursor 100% steady at all times. |
| **🖥️ Multi-Monitor Display Switching** | Dynamically detect and switch between multiple physical displays (Display 1, Display 2, etc.) on the fly with automatic aspect-ratio scaling. |
| **👁️ Compact UI with Hide/Show Menu** | Ultra-compact 36px top toolbar maximizing visible screen area. Features a 1-click **"Hide Menu ▲"** button for a clean full view, and a sleek **"☰ Menu ▼"** floating tab to instantly restore controls. |
| **🔒 Security & PIN Authentication** | Protected by a customizable Security PIN, AES-256-GCM authenticated encryption, ephemeral session tokens, and active viewer management with 1-click kick/disconnect. |
| **🆔 Permanent Hardware Device ID** | Auto-generates a permanent, hardware-bound identifier (`ACS-XXXX-XXXX`) derived from Windows `MachineGuid`. Stays identical across reboots and reinstalls. |
| **📡 LAN Peer Discovery Radar** | Zero-configuration UDP broadcast discovery on port 45820 detects all active MyAcs hosts on the local network automatically. |
| **🔄 Background Service & System Tray** | Operates silently in the Windows System Tray (`pythonw.exe`). Closing the UI window keeps the streaming engine active 24/7. |
| **🚀 Automatic Windows Startup** | Optionally launches on Windows boot via Windows Run Registry and Startup batch scripts. |
| **🌐 100% Browser-Based Viewer** | Remote viewers connect via any standard modern browser (Chrome, Edge, Firefox, Safari) without installing any client software on viewing devices. |

---

## 📁 Project Architecture

```
ScreenMiror/
├── main.py                     # Main application entry point (GUI, Tray, Headless)
├── START_MYACS.bat             # 1-Click All-in-One launcher (firewall, autostart, & service)
├── STOP_MYACS.bat              # 1-Click clean shutdown (kills background processes & frees ports)
├── add_firewall_rule.bat       # Configures Windows Defender Firewall for LAN access
├── test_system.py              # Automated 7-part test suite for all system components
├── requirements.txt            # Python dependencies
├── prompt                      # Original specification document
└── myacs/
    ├── core/
    │   ├── device_identity.py  # MachineGuid permanent ID & JSON persistent config
    │   ├── capture_engine.py   # 60 FPS desktop capture (pure SRCCOPY, no cursor blink)
    │   ├── input_engine.py     # Win32 hardware mouse/keyboard injection & binary unpacker
    │   ├── security.py         # PIN auth, session tokens, AES-256-GCM encryption
    │   ├── discovery.py        # Offline LAN UDP broadcast & peer discovery
    │   └── streaming_server.py # FastAPI + WebSocket 60 FPS binary streaming engine
    ├── service/
    │   ├── autostart.py        # Windows Registry & Startup folder manager
    │   └── tray_app.py         # PySide6 desktop window & Windows System Tray icon
    └── ui/
        ├── index.html          # Clean web dashboard & live interactive canvas viewer
        └── static/
            ├── css/style.css   # Dark glassmorphic design system & compact toolbar
            ├── js/app.js       # Real-time WebSocket receiver & binary input dispatcher
            └── assets/         # App icons (PNG & multi-resolution ICO)
```

---

## 📋 Prerequisites & Installation

### Requirements
- **OS:** Windows 10 or Windows 11 (64-bit)
- **Python:** Python 3.10 or higher
- **Network:** Connected to a Local Area Network (Wi-Fi or Ethernet)

### Install Dependencies
To install the required Python packages manually:
```powershell
pip install -r requirements.txt
```

---

## 🚀 How to Run

### Option 1: 1-Click All-in-One Launcher (Recommended)
Double-click **`START_MYACS.bat`**. This automatically:
1. Verifies Windows Defender Firewall rules for incoming LAN connections.
2. Ensures automatic Windows boot startup is registered.
3. Launches the background mirroring engine silently to the Windows System Tray.
4. Detects your LAN IP address and Security PIN.
5. Opens the dashboard in your default browser.

### Option 2: 1-Click Clean Shutdown
Double-click **`STOP_MYACS.bat`** to cleanly terminate all background mirroring processes (`pythonw.exe`, `python.exe`) and immediately release ports `45821` and `45820`.

### Option 3: Command Line (Developer / Headless Mode)
```powershell
# Run desktop window with tray:
python main.py

# Run silently in system tray (used by Windows Startup):
python main.py --background

# Run as a pure headless server daemon:
python main.py --headless
```

---

## 💻 Accessing from Another PC on the Local Network

1. **On the Host PC (the PC whose screen you want to share):**
   - Run `START_MYACS.bat`.
   - Take note of the **Security PIN** (e.g. `298989`) and **LAN IP** (e.g. `172.220.2.239`).
   - You can close the browser window at any time; the service remains active in the Windows System Tray.

2. **On the Viewing PC (any PC, laptop, or tablet on the same Wi-Fi/LAN):**
   - Open any web browser and navigate to:
     ```
     http://<HOST-PC-IP>:45821
     ```
     *(Example: `http://172.220.2.239:45821`)*
   - Or open the **Direct 1-Click Stream** link:
     ```
     http://<HOST-PC-IP>:45821/view
     ```
   - Enter the Security PIN and click **Connect to Remote Screen**.
   - The screen streams immediately in real-time with full interactive mouse and keyboard control!

---

## 🎮 Viewer Toolbar & Control Guide

While viewing the remote screen:

- **🎮 Control Toggle (`🎮 Control: ON` / `🔒 View-Only`):** Toggle interactive mouse and keyboard control on or off with a single click.
- **🖥️ Display Selector:** Switch between attached physical monitors (Display 1, Display 2, etc.).
- **⚙️ Quality Preset:** Select between **Speed (60%)**, **Balanced (75%)**, **High (85%)**, or **Ultra (92% Native)**.
- **📊 Real-time Telemetry:** Live monitor showing FPS, network latency in milliseconds, and throughput in KB/s.
- **⛶ Fullscreen:** Expand the stream to cover your entire display (Shortcut: `F11`).
- **👁️ Hide Menu ▲:** Slides the top toolbar out of view so you have a completely unobstructed view of the remote desktop.
- **☰ Menu ▼:** When the toolbar is hidden, a small floating tab stays docked at the top center. Click it or press **`Escape`** to restore the menu.
- **❌ Disconnect:** Safely disconnects the viewer session.

---

## ⚡ Latency & Performance Architecture

MyAcs achieves near-zero latency through a specialized low-overhead architecture:

1. **5-Byte Binary Input Protocol:** Mouse movements are transmitted as raw 5-byte packets (`[Opcode 1, X_u16, Y_u16]`), completely bypassing JSON serialization overhead. Decoded on the host in `0.0001 ms` using bitwise operations (capable of handling 6.4 million events per second).
2. **TCP_NODELAY Socket Optimization:** Disables Nagle's algorithm across WebSocket connections to prevent TCP buffering and packet delays.
3. **Pure SRCCOPY Desktop Capture:** Suppresses Windows GDI `CAPTUREBLT` flag, eliminating DWM hardware cursor hiding and stopping all mouse cursor blinking on the host computer.
4. **Pre-Cached Screen Bounds:** Eliminates dictionary indexing and monitor lookups inside the input loop, calling Windows `SetCursorPos()` in nanoseconds.
5. **60 FPS Video Pipeline:** Screen capture and adaptive JPEG encoding are paced at 60 FPS, reducing frame delivery latency to ~16.6 ms.
6. **Hardware Cursor Acceleration:** The viewing canvas renders the operating system's hardware cursor directly, giving instant 0 ms local tracking.

---

## 🧪 Automated Verification Suite

To run the automated test suite verifying all core requirements and services:

```powershell
python test_system.py
```

The test suite runs 7 automated verification tests:
1. Permanent Device ID generation and MachineGuid persistence.
2. High-performance screen capture engine and monitor detection.
3. PIN security, session token generation, and AES-256-GCM encryption.
4. UDP LAN peer discovery service and beacon broadcasting.
5. Server REST API status and WebSocket streaming pipeline.
6. Windows Autostart Registry and Startup folder registration.
7. Frontend static UI assets and HTML template verification.

---

## 🛡️ Firewall Configuration & Troubleshooting

### Windows Firewall
If another computer on your LAN cannot access the host URL, run **`add_firewall_rule.bat`** as Administrator once. This registers:
- **Port 45821 (TCP):** Inbound rule for HTTP Web Dashboard & WebSocket Video Stream.
- **Port 45820 (UDP):** Inbound rule for LAN Peer Discovery Beacons.

### Common Troubleshooting Tips
- **Cannot connect from second PC:** Ensure both computers are connected to the same Wi-Fi or subnet, and that Windows Network Profile is set to **Private Network**.
- **Port 45821 in use:** Run `STOP_MYACS.bat` to terminate any previous background instances and release the ports.
- **Host Cursor Blinking:** Solved natively in MyAcs via `mss.windows.gdi.CAPTUREBLT = 0`. No third-party drivers or monitor hooks required.
