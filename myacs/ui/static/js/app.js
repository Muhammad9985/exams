/**
 * MyAcs — Screen Mirroring & Interactive Remote Control Web Application
 * High-performance WebSocket receiver, Canvas 2D hardware-accelerated rendering,
 * bidirectional mouse & keyboard input streaming, real-time FPS/latency telemetry,
 * adaptive resolution, and automatic reconnection.
 */

// Application State
const state = {
  myDeviceId: "",
  myDeviceName: "",
  myPin: "",
  lanIps: [],
  activeViewers: [],
  
  // Active Viewer Session
  streamingWs: null,
  isViewerActive: false,
  isControlEnabled: true,  // Mouse & Keyboard enabled by default
  currentTargetId: "",
  currentTargetIp: "",
  currentTargetPort: 45821,
  currentTargetPin: "",
  reconnectAttempts: 0,
  reconnectTimer: null,
  isManualDisconnect: false,
  hasAutoLaunched: false,
  
  // Performance Tracking
  framesReceived: 0,
  bytesReceived: 0,
  currentFps: 0,
  currentLatencyMs: 0,
  currentKbps: 0,
  statsInterval: null,
  lastStatsTime: Date.now(),
  lastBytesCount: 0,
  lastFrameCount: 0,
};

// DOM Elements
const elements = {
  myDeviceId: document.getElementById("myDeviceId"),
  myDeviceName: document.getElementById("myDeviceName"),
  myPin: document.getElementById("myPin"),
  lanIpBadge: document.getElementById("lanIpBadge"),
  shareUrlText: document.getElementById("shareUrlText"),
  autostartToggle: document.getElementById("autostartToggle"),
  remoteControlToggle: document.getElementById("remoteControlToggle"),
  activeViewersCount: document.getElementById("activeViewersCount"),
  activeViewersList: document.getElementById("activeViewersList"),
  
  // Viewer Modal & Canvas
  viewerModal: document.getElementById("viewerModal"),
  viewerToolbar: document.getElementById("viewerToolbar"),
  btnShowMenu: document.getElementById("btnShowMenu"),
  btnHideMenu: document.getElementById("btnHideMenu"),
  screenCanvas: document.getElementById("screenCanvas"),
  viewerTargetTitle: document.getElementById("viewerTargetTitle"),
  viewerStats: document.getElementById("viewerStats"),
  viewerMonitorSelect: document.getElementById("viewerMonitorSelect"),
  viewerQualitySelect: document.getElementById("viewerQualitySelect"),
  reconnectBanner: document.getElementById("reconnectBanner"),
  btnControlToggle: document.getElementById("btnControlToggle"),
};

// Canvas 2D Context
const canvas = elements.screenCanvas;
const ctx = canvas.getContext("2d", { alpha: false });

// -------------------------------------------------------------
// Initialization & Polling
// -------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  fetchHostStatus();
  initRemoteInputListeners();
  // Periodic polling for status and active viewers
  setInterval(fetchHostStatus, 2500);
});

// -------------------------------------------------------------
// Host API Interactions
// -------------------------------------------------------------

async function fetchHostStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    
    state.myDeviceId = data.device_id;
    state.myDeviceName = data.device_name;
    state.myPin = data.security_pin;
    state.lanIps = data.lan_ips || [];
    state.activeViewers = data.active_viewers || [];

    if (elements.myDeviceId) elements.myDeviceId.innerText = data.device_id;
    if (elements.myDeviceName) elements.myDeviceName.innerText = data.device_name;
    if (elements.myPin) elements.myPin.value = data.security_pin;
    if (elements.autostartToggle) elements.autostartToggle.checked = !!data.autostart;
    if (elements.remoteControlToggle && data.allow_remote_control !== undefined) {
      elements.remoteControlToggle.checked = !!data.allow_remote_control;
    }
    
    const primaryIp = state.lanIps[0] || window.location.hostname || "127.0.0.1";
    const port = data.port || 45821;
    if (elements.lanIpBadge) {
      elements.lanIpBadge.innerText = `${primaryIp}:${port}`;
    }
    if (elements.shareUrlText) {
      elements.shareUrlText.innerText = `http://${primaryIp}:${port}/view`;
    }

    // Check if being accessed from another PC on LAN
    const isRemoteViewer = window.location.hostname !== "127.0.0.1" && window.location.hostname !== "localhost";
    const hero = document.getElementById("remoteViewerHero");
    const heroName = document.getElementById("heroHostName");
    if (hero) {
      if (isRemoteViewer) {
        hero.style.display = "block";
        if (heroName) heroName.innerText = data.device_name || "Remote Host";
      } else {
        hero.style.display = "none";
      }
    }

    // If navigated to /view or ?view=true, auto-launch screen stream immediately
    if (!state.isViewerActive && !state.hasAutoLaunched) {
      if (window.location.pathname === "/view" || window.location.search.includes("view=true")) {
        state.hasAutoLaunched = true;
        viewThisHostScreen();
      }
    }

    renderActiveViewers(data.active_viewers);
  } catch (err) {
    console.error("Error fetching host status:", err);
  }
}

function renderActiveViewers(viewers) {
  if (!elements.activeViewersCount || !elements.activeViewersList) return;
  elements.activeViewersCount.innerText = viewers.length;

  if (viewers.length === 0) {
    elements.activeViewersList.innerHTML = `<p style="color: var(--text-dim); font-size: 0.85rem;">No active viewers connected.</p>`;
    return;
  }

  elements.activeViewersList.innerHTML = viewers.map(v => `
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0; border-bottom: 1px solid var(--border-subtle);">
      <div>
        <div style="font-weight: 600; font-size: 0.9rem;">${escapeHtml(v.viewer_name)} (${v.viewer_device_id})</div>
        <div style="font-size: 0.75rem; color: var(--text-muted);">${v.client_ip} • Connected ${v.duration_seconds}s</div>
      </div>
      <button class="btn-danger" onclick="disconnectViewer('${v.token}')">Disconnect</button>
    </div>
  `).join("");
}

function viewThisHostScreen(pinOverride) {
  const pin = pinOverride || (elements.myPin && elements.myPin.value ? elements.myPin.value.trim() : (state.myPin || ""));
  
  state.currentTargetId = state.myDeviceId || "THIS-PC";
  state.currentTargetIp = window.location.hostname || "127.0.0.1";
  state.currentTargetPort = window.location.port ? parseInt(window.location.port) : 45821;
  state.currentTargetPin = pin;
  state.isManualDisconnect = false;
  state.reconnectAttempts = 0;
  
  connectWebSocketStream();
}

// -------------------------------------------------------------
// Copy & Settings Updates
// -------------------------------------------------------------

function copyDeviceId() {
  const id = state.myDeviceId || (elements.myDeviceId ? elements.myDeviceId.innerText : "");
  if (!id) return;
  navigator.clipboard.writeText(id).then(() => {
    showToast(`Copied ${id} to clipboard!`);
  }).catch(() => {
    showToast("Clipboard access denied. Please copy manually.");
  });
}

function copyLanUrl() {
  const primaryIp = state.lanIps[0] || window.location.hostname || "127.0.0.1";
  const port = window.location.port || 45821;
  const url = `http://${primaryIp}:${port}/view`;
  navigator.clipboard.writeText(url).then(() => {
    showToast(`Copied LAN Viewer URL: ${url}`);
  }).catch(() => {
    showToast(`LAN URL: ${url}`);
  });
}

async function updatePin() {
  const newPin = elements.myPin.value.trim();
  if (newPin.length < 4) {
    showToast("PIN must be at least 4 characters.");
    return;
  }
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ security_pin: newPin })
    });
    if (res.ok) {
      showToast("Security PIN updated successfully!");
    }
  } catch (err) {
    showToast("Failed to update PIN.");
  }
}

async function toggleAutostart() {
  const enabled = elements.autostartToggle.checked;
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ autostart: enabled })
    });
    if (res.ok) {
      showToast(enabled ? "Windows Auto-Start enabled." : "Windows Auto-Start disabled.");
    }
  } catch (err) {
    showToast("Failed to update Auto-Start.");
  }
}

async function toggleRemoteControlSetting() {
  const toggle = elements.remoteControlToggle || document.getElementById("remoteControlToggle");
  const enabled = toggle ? toggle.checked : true;
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ allow_remote_control: enabled })
    });
    if (res.ok) {
      showToast(enabled ? "Remote Control enabled for LAN viewers." : "Remote Control disabled (View-Only enforced).");
    }
  } catch (err) {
    showToast("Failed to update setting.");
  }
}

async function disconnectViewer(token) {
  try {
    await fetch("/api/sessions/disconnect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token })
    });
    fetchHostStatus();
    showToast("Viewer disconnected.");
  } catch (err) {
    console.error(err);
  }
}

// -------------------------------------------------------------
// Interactive Remote Input Handlers (Mouse & Keyboard)
// -------------------------------------------------------------

function initRemoteInputListeners() {
  if (!canvas) return;

  // Pre-allocated binary packet buffers for instant, zero-allocation dispatch
  const moveBuf = new ArrayBuffer(5);
  const moveView = new DataView(moveBuf);
  moveView.setUint8(0, 1); // Opcode 1 = mouse_move

  const btnBuf = new ArrayBuffer(6);
  const btnView = new DataView(btnBuf);

  const scrollBuf = new ArrayBuffer(5);
  const scrollView = new DataView(scrollBuf);
  scrollView.setUint8(0, 4); // Opcode 4 = mouse_scroll

  let lastSentU16X = -1;
  let lastSentU16Y = -1;

  function getNormalizedCoords(e) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return { x: 0, y: 0 };
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    return { x, y };
  }

  function sendInput(data) {
    if (!state.streamingWs || state.streamingWs.readyState !== WebSocket.OPEN) return;
    if (!state.isViewerActive || !state.isControlEnabled) return;
    state.streamingWs.send(JSON.stringify(data));
  }

  // 1. Mouse Movement (Direct, zero-latency binary dispatch)
  canvas.addEventListener("mousemove", (e) => {
    if (!state.isViewerActive || !state.isControlEnabled) return;
    if (!state.streamingWs || state.streamingWs.readyState !== WebSocket.OPEN) return;

    const { x, y } = getNormalizedCoords(e);
    const u16X = Math.round(x * 65535);
    const u16Y = Math.round(y * 65535);

    // Suppress only exact identical positions (0.03 pixel resolution)
    if (u16X === lastSentU16X && u16Y === lastSentU16Y) return;

    lastSentU16X = u16X;
    lastSentU16Y = u16Y;

    moveView.setUint16(1, u16X);
    moveView.setUint16(3, u16Y);
    state.streamingWs.send(moveBuf);
  });

  // 2. Mouse Down (Instant binary click start)
  canvas.addEventListener("mousedown", (e) => {
    if (!state.isControlEnabled || !state.streamingWs || state.streamingWs.readyState !== WebSocket.OPEN) return;
    const { x, y } = getNormalizedCoords(e);
    const btnCode = e.button === 2 ? 2 : (e.button === 1 ? 1 : 0);
    btnView.setUint8(0, 2); // Opcode 2 = mouse_down
    btnView.setUint8(1, btnCode);
    btnView.setUint16(2, Math.round(x * 65535));
    btnView.setUint16(4, Math.round(y * 65535));
    state.streamingWs.send(btnBuf);
  });

  // 3. Mouse Up (Instant binary click release)
  canvas.addEventListener("mouseup", (e) => {
    if (!state.isControlEnabled || !state.streamingWs || state.streamingWs.readyState !== WebSocket.OPEN) return;
    const { x, y } = getNormalizedCoords(e);
    const btnCode = e.button === 2 ? 2 : (e.button === 1 ? 1 : 0);
    btnView.setUint8(0, 3); // Opcode 3 = mouse_up
    btnView.setUint8(1, btnCode);
    btnView.setUint16(2, Math.round(x * 65535));
    btnView.setUint16(4, Math.round(y * 65535));
    state.streamingWs.send(btnBuf);
  });

  // 4. Double Click
  canvas.addEventListener("dblclick", (e) => {
    if (!state.isControlEnabled) return;
    const { x, y } = getNormalizedCoords(e);
    sendInput({ type: "mouse_click", button: "left", x, y, clicks: 2 });
  });

  // 5. Intercept Context Menu (Right Click)
  canvas.addEventListener("contextmenu", (e) => {
    if (state.isViewerActive && state.isControlEnabled) {
      e.preventDefault();
    }
  });

  // 6. Mouse Wheel Scroll (Instant binary scroll)
  canvas.addEventListener("wheel", (e) => {
    if (state.isViewerActive && state.isControlEnabled && state.streamingWs && state.streamingWs.readyState === WebSocket.OPEN) {
      e.preventDefault();
      scrollView.setInt16(1, Math.round(e.deltaX));
      scrollView.setInt16(3, Math.round(e.deltaY));
      state.streamingWs.send(scrollBuf);
    }
  }, { passive: false });

  // 7. Keyboard Input (Key Down)
  window.addEventListener("keydown", (e) => {
    if (!state.isViewerActive || !state.isControlEnabled) return;
    // Don't capture when typing inside form inputs
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT")) {
      return;
    }

    // Prevent browser navigation/scrolling on common control keys
    if (["Tab", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space", "F5", "F11"].includes(e.code) || e.key === "Tab") {
      e.preventDefault();
    }

    sendInput({
      type: "key_down",
      key: e.key,
      code: e.code,
      ctrl: e.ctrlKey,
      shift: e.shiftKey,
      alt: e.altKey,
      meta: e.metaKey
    });
  });

  // 8. Keyboard Input (Key Up)
  window.addEventListener("keyup", (e) => {
    if (!state.isViewerActive || !state.isControlEnabled) return;
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT")) {
      return;
    }

    sendInput({
      type: "key_up",
      key: e.key,
      code: e.code,
      ctrl: e.ctrlKey,
      shift: e.shiftKey,
      alt: e.altKey,
      meta: e.metaKey
    });
  });
}

function toggleControlMode() {
  state.isControlEnabled = !state.isControlEnabled;
  updateControlUi();
  showToast(state.isControlEnabled ? "🎮 Remote Control ON: Mouse & keyboard active." : "🔒 View-Only Mode: Remote input paused.");
}

function updateControlUi() {
  const btn = elements.btnControlToggle || document.getElementById("btnControlToggle");
  if (btn) {
    if (state.isControlEnabled) {
      btn.style.background = "rgba(34, 197, 94, 0.2)";
      btn.style.borderColor = "rgba(34, 197, 94, 0.4)";
      btn.style.color = "#4ade80";
      btn.innerHTML = "<span>🎮 Control: ON</span>";
    } else {
      btn.style.background = "rgba(148, 163, 184, 0.2)";
      btn.style.borderColor = "rgba(148, 163, 184, 0.4)";
      btn.style.color = "#94a3b8";
      btn.innerHTML = "<span>🔒 View-Only</span>";
    }
  }
}

// -------------------------------------------------------------
// Screen Mirroring Client WebSocket Engine
// -------------------------------------------------------------

function connectWebSocketStream() {
  if (state.streamingWs) {
    try { state.streamingWs.close(); } catch (e) {}
    state.streamingWs = null;
  }

  const targetIp = state.currentTargetIp || window.location.hostname || "127.0.0.1";
  const targetPort = state.currentTargetPort || (window.location.port ? parseInt(window.location.port) : 45821);
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${targetIp}:${targetPort}/ws/stream`;

  showToast(`Connecting to ${targetIp}:${targetPort}...`);

  try {
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";
    state.streamingWs = ws;

    let nextExpectedType = "header";
    let currentFrameHeader = null;

    ws.onopen = () => {
      console.log("[Viewer] WebSocket connected, sending auth handshake...");
      // Send authentication handshake
      ws.send(JSON.stringify({
        type: "auth",
        pin: state.currentTargetPin,
        viewer_device_id: state.myDeviceId || "REMOTE-VIEWER",
        viewer_name: "LAN Viewer"
      }));
    };

    ws.onmessage = async (event) => {
      // 1. Text control/metadata message
      if (typeof event.data === "string") {
        try {
          const msg = jsonParseSafe(event.data);
          if (!msg) return;

          if (msg.type === "auth_success") {
            onAuthenticationSuccess(msg);
          } else if (msg.type === "auth_error") {
            showToast(`Authentication failed: ${msg.message}`);
            closeViewer();
          } else if (msg.type === "frame_header") {
            currentFrameHeader = msg;
            nextExpectedType = "binary";
          } else if (msg.type === "warning") {
            showToast(msg.message);
          }
        } catch (e) {
          console.error("JSON parse error:", e);
        }
      } 
      // 2. Binary frame payload (JPEG image bytes)
      else if (event.data instanceof ArrayBuffer) {
        if (currentFrameHeader) {
          renderFrameBuffer(event.data, currentFrameHeader);
          currentFrameHeader = null;
          nextExpectedType = "header";
        }
      }
    };

    ws.onclose = (event) => {
      console.log("[Viewer] WebSocket closed:", event);
      if (!state.isManualDisconnect && state.isViewerActive) {
        triggerAutoReconnect();
      }
    };

    ws.onerror = (err) => {
      console.error("[Viewer] WebSocket error:", err);
    };

  } catch (err) {
    console.error("Connection failed:", err);
    if (!state.isManualDisconnect) triggerAutoReconnect();
  }
}

function onAuthenticationSuccess(data) {
  state.isViewerActive = true;
  state.reconnectAttempts = 0;
  hideReconnectBanner();
  showViewerToolbar();
  updateControlUi();

  if (elements.viewerModal) elements.viewerModal.classList.add("active");
  if (elements.viewerTargetTitle) {
    elements.viewerTargetTitle.innerText = `${data.host_name || "Remote PC"} (${data.host_device_id || state.myDeviceId})`;
  }

  // Populate monitors selector
  if (elements.viewerMonitorSelect && data.monitors) {
    elements.viewerMonitorSelect.innerHTML = data.monitors.map(m => `
      <option value="${m.index}">Display ${m.index} (${m.width}x${m.height})</option>
    `).join("");
    elements.viewerMonitorSelect.value = data.selected_monitor || 1;
  }

  startPerformanceStatsTracking();
  showToast("Connected! Mouse and keyboard control active.");
}

function renderFrameBuffer(arrayBuffer, header) {
  state.framesReceived++;
  state.bytesReceived += arrayBuffer.byteLength;

  // Calculate latency from header timestamp to render
  if (header.timestamp) {
    state.currentLatencyMs = Math.max(1, Math.round((Date.now() / 1000 - header.timestamp) * 1000));
  }

  // Create Blob and draw to canvas via ImageBitmap (Peak 60 FPS performance)
  const blob = new Blob([arrayBuffer], { type: "image/jpeg" });
  createImageBitmap(blob).then(bitmap => {
    if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
    }
    ctx.drawImage(bitmap, 0, 0);
    bitmap.close();
  }).catch(err => {
    // Fallback image rendering if ImageBitmap fails
    const img = new Image();
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      if (canvas.width !== img.width || canvas.height !== img.height) {
        canvas.width = img.width;
        canvas.height = img.height;
      }
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
    };
    img.src = url;
  });
}

// -------------------------------------------------------------
// Auto-Reconnection Loop
// -------------------------------------------------------------

function triggerAutoReconnect() {
  if (state.isManualDisconnect) return;
  state.reconnectAttempts++;
  
  const delaySec = Math.min(10, Math.pow(1.5, state.reconnectAttempts));
  showReconnectBanner(state.reconnectAttempts, Math.round(delaySec));

  clearTimeout(state.reconnectTimer);
  state.reconnectTimer = setTimeout(() => {
    if (!state.isManualDisconnect && state.isViewerActive) {
      console.log(`[Reconnection] Attempt #${state.reconnectAttempts}...`);
      connectWebSocketStream();
    }
  }, delaySec * 1000);
}

function showReconnectBanner(attempt, seconds) {
  if (elements.reconnectBanner) {
    elements.reconnectBanner.style.display = "block";
    elements.reconnectBanner.innerText = `⚠️ Connection lost. Auto-reconnecting in ${seconds}s... (Attempt ${attempt})`;
  }
}

function hideReconnectBanner() {
  if (elements.reconnectBanner) elements.reconnectBanner.style.display = "none";
}

// -------------------------------------------------------------
// Controls & Viewer Actions
// -------------------------------------------------------------

function hideViewerToolbar() {
  const toolbar = elements.viewerToolbar || document.getElementById("viewerToolbar");
  const showBtn = elements.btnShowMenu || document.getElementById("btnShowMenu");
  if (toolbar) toolbar.classList.add("hidden");
  if (showBtn) showBtn.classList.add("visible");
}

function showViewerToolbar() {
  const toolbar = elements.viewerToolbar || document.getElementById("viewerToolbar");
  const showBtn = elements.btnShowMenu || document.getElementById("btnShowMenu");
  if (toolbar) toolbar.classList.remove("hidden");
  if (showBtn) showBtn.classList.remove("visible");
}

function closeViewer() {
  state.isManualDisconnect = true;
  state.isViewerActive = false;
  clearTimeout(state.reconnectTimer);
  stopPerformanceStatsTracking();
  showViewerToolbar();

  if (state.streamingWs) {
    try { state.streamingWs.close(); } catch (e) {}
    state.streamingWs = null;
  }

  if (elements.viewerModal) elements.viewerModal.classList.remove("active");
  hideReconnectBanner();
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    if (elements.viewerModal.requestFullscreen) {
      elements.viewerModal.requestFullscreen();
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen();
    }
  }
}

function changeQualityPreset() {
  const mode = elements.viewerQualitySelect.value;
  if (state.streamingWs && state.streamingWs.readyState === WebSocket.OPEN) {
    state.streamingWs.send(JSON.stringify({
      type: "set_quality",
      mode: mode
    }));
    showToast(`Quality adjusted to: ${mode}`);
  }
}

function changeMonitorSelection() {
  const index = parseInt(elements.viewerMonitorSelect.value);
  if (state.streamingWs && state.streamingWs.readyState === WebSocket.OPEN) {
    state.streamingWs.send(JSON.stringify({
      type: "set_monitor",
      index: index
    }));
    showToast(`Switched to Display ${index}`);
  }
}

// -------------------------------------------------------------
// Stats Tracking & Utilities
// -------------------------------------------------------------

function startPerformanceStatsTracking() {
  stopPerformanceStatsTracking();
  state.lastStatsTime = Date.now();
  state.lastBytesCount = state.bytesReceived;
  state.lastFrameCount = state.framesReceived;

  state.statsInterval = setInterval(() => {
    const now = Date.now();
    const elapsedSec = (now - state.lastStatsTime) / 1000;
    if (elapsedSec <= 0) return;

    const framesDelta = state.framesReceived - state.lastFrameCount;
    const bytesDelta = state.bytesReceived - state.lastBytesCount;

    state.currentFps = Math.round(framesDelta / elapsedSec);
    state.currentKbps = Math.round((bytesDelta / 1024) / elapsedSec);

    state.lastStatsTime = now;
    state.lastBytesCount = state.bytesReceived;
    state.lastFrameCount = state.framesReceived;

    if (elements.viewerStats) {
      elements.viewerStats.innerText = `${state.currentFps} FPS | ${state.currentLatencyMs} ms | ${state.currentKbps} KB/s`;
    }
  }, 1000);
}

function stopPerformanceStatsTracking() {
  if (state.statsInterval) {
    clearInterval(state.statsInterval);
    state.statsInterval = null;
  }
}

function showToast(message) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerText = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, 3500);
}

function escapeHtml(text) {
  if (!text) return "";
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function jsonParseSafe(str) {
  try { return JSON.parse(str); } catch (e) { return null; }
}
