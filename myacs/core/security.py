"""
MyAcs — Security, Authentication & Local Network Encryption
Provides PIN verification, AES-256-GCM encryption for video streams and control messages,
session token lifecycle, and viewer authorization whitelisting.
"""

import os
import time
import hmac
import hashlib
import secrets
from typing import Dict, Optional, Tuple, Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from myacs.core.device_identity import config


class SessionManager:
    """Manages authenticated viewer sessions and encryption keys."""

    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    def derive_key(self, pin: str, salt: bytes) -> bytes:
        """Derive a 256-bit AES key from the security PIN and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=50_000,
        )
        return kdf.derive(pin.encode("utf-8"))

    def authenticate(
        self,
        provided_pin: str,
        viewer_device_id: str,
        viewer_name: str,
        client_ip: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Validates authentication request against current host security configuration.
        Returns: (success, message, session_token)
        """
        expected_pin = str(config.get("security_pin", "")).strip()
        require_pin = config.get("require_pin", True)
        allowed_viewers = config.get("allowed_viewers", [])

        # Check if viewer is explicitly whitelisted
        is_whitelisted = viewer_device_id and viewer_device_id in allowed_viewers

        if require_pin and not is_whitelisted:
            if not provided_pin:
                return False, "Security PIN is required to view this device.", None
            
            # Constant-time comparison to prevent timing attacks
            if not hmac.compare_digest(provided_pin.strip(), expected_pin):
                return False, "Invalid Security PIN.", None

        # Create session
        token = secrets.token_hex(24)
        salt = os.urandom(16)
        aes_key = self.derive_key(expected_pin or "MyAcsLANKey", salt)

        session_data = {
            "token": token,
            "viewer_device_id": viewer_device_id or "Unknown",
            "viewer_name": viewer_name or "Viewer",
            "client_ip": client_ip,
            "authenticated_at": time.time(),
            "last_activity": time.time(),
            "frames_sent": 0,
            "bytes_sent": 0,
            "salt": salt,
            "aes_key": aes_key,
            "aesgcm": AESGCM(aes_key)
        }
        self.active_sessions[token] = session_data

        return True, "Authenticated successfully.", token

    def validate_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify session token validity and update activity."""
        session = self.active_sessions.get(token)
        if not session:
            return None
        session["last_activity"] = time.time()
        return session

    def close_session(self, token: str):
        if token in self.active_sessions:
            del self.active_sessions[token]

    def encrypt_payload(self, token: str, data: bytes) -> Optional[bytes]:
        """
        Encrypts a data payload using AES-256-GCM with a fresh 96-bit nonce.
        Format: [12-byte Nonce] + [Ciphertext + 16-byte Tag]
        """
        session = self.active_sessions.get(token)
        if not session:
            return None
        nonce = os.urandom(12)
        ciphertext = session["aesgcm"].encrypt(nonce, data, None)
        return nonce + ciphertext

    def decrypt_payload(self, token: str, encrypted_data: bytes) -> Optional[bytes]:
        """Decrypts an AES-256-GCM payload."""
        session = self.active_sessions.get(token)
        if not session or len(encrypted_data) < 28:
            return None
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        try:
            return session["aesgcm"].decrypt(nonce, ciphertext, None)
        except Exception:
            return None

    def get_active_sessions_summary(self) -> list:
        now = time.time()
        summary = []
        for token, s in list(self.active_sessions.items()):
            # Expire sessions with no activity for 60 seconds
            if now - s["last_activity"] > 60:
                self.close_session(token)
                continue
            summary.append({
                "token": token,
                "viewer_device_id": s["viewer_device_id"],
                "viewer_name": s["viewer_name"],
                "client_ip": s["client_ip"],
                "duration_seconds": int(now - s["authenticated_at"]),
                "frames_sent": s["frames_sent"],
                "bytes_sent": s["bytes_sent"],
            })
        return summary


# Global singleton instance
session_manager = SessionManager()
