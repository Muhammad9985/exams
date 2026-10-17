"""
MyAcs — Local Area Network (LAN) Peer Discovery
Operates 100% offline over UDP broadcast and directed subnet probes.
Automatically maps Permanent Device IDs (ACS-XXXX-XXXX) to LAN IP addresses
and provides real-time list of online MyAcs PCs.
"""

import time
import json
import socket
import threading
from typing import Dict, Any, List, Optional
from myacs.core.device_identity import config


def get_all_lan_ips() -> List[str]:
    """Retrieve all active IPv4 addresses on local network interfaces without external DLL dependencies."""
    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.append(ip)
    except Exception:
        pass

    # Secondary check via UDP interface route discovery
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        local_ip = s.getsockname()[0]
        s.close()
        if local_ip and not local_ip.startswith("127."):
            ips.append(local_ip)
    except Exception:
        pass

    if not ips:
        ips.append("127.0.0.1")

    return list(dict.fromkeys(ips))


class LanDiscoveryService:
    """Handles background UDP beacons, targeted probes, and peer tracking."""

    def __init__(self, port: int = 45820):
        self.port = port
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.discovered_peers: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self._listener_thread: Optional[threading.Thread] = None
        self._beacon_thread: Optional[threading.Thread] = None

    def start(self):
        """Starts discovery listener and beacon broadcasting threads."""
        if self.running:
            return
        self.running = True
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.bind(("0.0.0.0", self.port))
            self.sock.settimeout(1.0)
        except Exception as e:
            print(f"[Discovery] Failed to bind UDP discovery socket: {e}")
            self.running = False
            return

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True, name="MyAcsDiscoveryListen")
        self._listener_thread.start()

        self._beacon_thread = threading.Thread(target=self._beacon_loop, daemon=True, name="MyAcsDiscoveryBeacon")
        self._beacon_thread.start()
        print(f"[Discovery] LAN Discovery Service started on UDP port {self.port}")

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _listen_loop(self):
        """Continuously listens for peer broadcasts and probe queries."""
        my_id = config.get("device_id")
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                if not data:
                    continue
                packet = json.loads(data.decode("utf-8"))
                pkt_type = packet.get("type")
                sender_id = packet.get("device_id")

                # Ignore packets originating from this exact local instance
                if sender_id == my_id:
                    continue

                now = time.time()
                sender_ip = addr[0]

                if pkt_type == "BEACON" or pkt_type == "PONG":
                    with self.lock:
                        self.discovered_peers[sender_id] = {
                            "device_id": sender_id,
                            "device_name": packet.get("device_name", "Remote PC"),
                            "ip": sender_ip,
                            "port": packet.get("port", 45821),
                            "require_pin": packet.get("require_pin", True),
                            "quality": packet.get("quality", "balanced"),
                            "last_seen": now
                        }

                elif pkt_type == "PROBE":
                    target_id = packet.get("target_id")
                    # If this probe is looking for us, reply immediately with PONG
                    if target_id == my_id or target_id == "*":
                        reply = {
                            "type": "PONG",
                            "device_id": my_id,
                            "device_name": config.get("device_name"),
                            "port": config.get("port", 45821),
                            "require_pin": config.get("require_pin", True),
                            "quality": config.get("quality", "balanced"),
                            "timestamp": now
                        }
                        reply_bytes = json.dumps(reply).encode("utf-8")
                        self.sock.sendto(reply_bytes, addr)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    # Ignore occasional malformed packet
                    pass

    def _beacon_loop(self):
        """Periodically broadcasts this PC's availability to the local network."""
        while self.running:
            self.broadcast_beacon()
            # Clean up peers that haven't sent a beacon in 15 seconds
            with self.lock:
                now = time.time()
                expired = [pid for pid, p in self.discovered_peers.items() if now - p["last_seen"] > 15]
                for pid in expired:
                    del self.discovered_peers[pid]
            time.sleep(3.5)

    def broadcast_beacon(self):
        """Send availability beacon to 255.255.255.255 and subnet broadcasts."""
        if not self.sock:
            return
        payload = {
            "type": "BEACON",
            "device_id": config.get("device_id"),
            "device_name": config.get("device_name"),
            "port": config.get("port", 45821),
            "require_pin": config.get("require_pin", True),
            "quality": config.get("quality", "balanced"),
            "timestamp": time.time()
        }
        data = json.dumps(payload).encode("utf-8")

        # Broadcast to standard LAN broadcast
        try:
            self.sock.sendto(data, ("255.255.255.255", self.port))
        except Exception:
            pass

        # Also broadcast on all specific subnet broadcast addresses (e.g. 192.168.1.255)
        for ip in get_all_lan_ips():
            parts = ip.split(".")
            if len(parts) == 4:
                subnet_broadcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
                try:
                    self.sock.sendto(data, (subnet_broadcast, self.port))
                except Exception:
                    pass

    def probe_device(self, target_device_id: str, timeout_sec: float = 2.0) -> Optional[Dict[str, Any]]:
        """
        Sends an active probe for a target device ID and waits briefly for its response.
        Returns the peer details if found, or checks current cache.
        """
        target_device_id = target_device_id.strip().upper()
        my_id = (config.get("device_id") or "").strip().upper()

        # If probing for THIS host machine, return local instance immediately
        if target_device_id == my_id:
            ips = get_all_lan_ips()
            return {
                "device_id": my_id,
                "device_name": config.get("device_name"),
                "ip": ips[0] if ips else "127.0.0.1",
                "port": config.get("port", 45821),
                "require_pin": config.get("require_pin", True),
                "quality": config.get("quality", "balanced"),
                "last_seen": time.time()
            }

        # Check cache first
        with self.lock:
            if target_device_id in self.discovered_peers:
                peer = self.discovered_peers[target_device_id]
                if time.time() - peer["last_seen"] < 15:
                    return peer

        # Send active probe
        if not self.sock:
            return None

        probe_pkt = {
            "type": "PROBE",
            "target_id": target_device_id,
            "device_id": config.get("device_id"),
            "timestamp": time.time()
        }
        probe_bytes = json.dumps(probe_pkt).encode("utf-8")

        try:
            self.sock.sendto(probe_bytes, ("255.255.255.255", self.port))
            for ip in get_all_lan_ips():
                parts = ip.split(".")
                if len(parts) == 4:
                    self.sock.sendto(probe_bytes, (f"{parts[0]}.{parts[1]}.{parts[2]}.255", self.port))
        except Exception:
            pass

        # Wait up to timeout_sec for response in cache
        start_wait = time.time()
        while time.time() - start_wait < timeout_sec:
            with self.lock:
                if target_device_id in self.discovered_peers:
                    return self.discovered_peers[target_device_id]
            time.sleep(0.1)

        return None

    def get_online_peers(self) -> List[Dict[str, Any]]:
        """Returns sorted list of currently available MyAcs devices on LAN."""
        with self.lock:
            now = time.time()
            return [
                p for p in self.discovered_peers.values()
                if now - p["last_seen"] <= 15
            ]


# Global singleton instance
lan_discovery = LanDiscoveryService()
