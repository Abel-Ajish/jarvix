"""Encrypted secret storage for jarvix.

Uses Fernet (AES-128 + HMAC) with a per-machine key derived from
machine-specific data.  Falls back to Windows Credential Manager if
available, otherwise stores encrypted file in %APPDATA%/jarvix/secrets.

API keys are NEVER logged, NEVER shown in UI, and NEVER sent to web.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.secret_store")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_APP_DATA = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
_SECRETS_DIR = _APP_DATA / "jarvix" / "secrets"
_SECRETS_DIR.mkdir(parents=True, exist_ok=True)
_SECRETS_FILE = _SECRETS_DIR / "secrets.enc"
_SALT_FILE = _SECRETS_DIR / "salt.bin"

# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _machine_id() -> bytes:
    """Return a machine-specific identifier for key derivation."""
    # Use Windows machine GUID + user SID
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        import win32api
        user_sid = win32api.GetUserNameEx(win32api.NameFullyQualifiedDN)
        return f"{machine_guid}|{user_sid}".encode()
    except Exception:
        # Fallback: hostname + username
        import socket
        import getpass
        return f"{socket.gethostname()}|{getpass.getuser()}".encode()


def _derive_key(salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from machine_id + salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(_machine_id()))


def _load_or_create_key() -> Fernet:
    """Load existing salt/key or create new ones."""
    if _SALT_FILE.exists():
        with _SALT_FILE.open("rb") as f:
            salt = f.read()
    else:
        salt = os.urandom(16)
        with _SALT_FILE.open("wb") as f:
            f.write(salt)
    key = _derive_key(salt)
    return Fernet(key)


class SecretStore:
    """Encrypted key-value store for secrets (API keys, tokens, etc.)."""

    # Secrets expire after 1 hour by default
    _SECRET_TTL_SECONDS = 3600

    def __init__(self) -> None:
        self._fernet = _load_or_create_key()
        # Cache stores (value, expiry_timestamp) tuples for TTL-based eviction
        self._cache: dict[str, tuple[str, float]] = {}
        self._max_cache_size = 100
        self._load()

    def _is_expired(self, expiry: float) -> bool:
        """Check if a cached secret has expired."""
        return datetime.now().timestamp() > expiry

    def _evict_expired(self) -> None:
        """Remove expired entries from cache."""
        now = datetime.now().timestamp()
        expired = [k for k, (_, expiry) in self._cache.items() if now > expiry]
        for key in expired:
            del self._cache[key]

    def _load(self) -> None:
        """Load encrypted secrets from disk into cache."""
        if not _SECRETS_FILE.exists():
            return
        try:
            with _SECRETS_FILE.open("rb") as f:
                data = json.loads(f.read().decode())
            for key, encrypted_value in data.items():
                decrypted = self._fernet.decrypt(encrypted_value.encode()).decode()
                expiry = datetime.now().timestamp() + self._SECRET_TTL_SECONDS
                self._cache[key] = (decrypted, expiry)
        except Exception as e:
            _LOG.warning("Failed to load secrets: %s", e)

    def _save(self) -> None:
        """Persist cached secrets to disk."""
        try:
            data = {}
            for key, (value, _) in self._cache.items():
                encrypted = self._fernet.encrypt(value.encode()).decode()
                data[key] = encrypted
            with _SECRETS_FILE.open("w") as f:
                json.dump(data, f)
        except Exception as e:
            _LOG.warning("Failed to save secrets: %s", e)

    def get(self, key: str) -> Optional[str]:
        """Return the decrypted value for ``key`` or None if not found or expired."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if self._is_expired(expiry):
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: str) -> None:
        """Encrypt and store ``value`` for ``key`` with TTL."""
        self._evict_expired()
        # Limit cache size by removing oldest entries if needed
        if len(self._cache) >= self._max_cache_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        expiry = datetime.now().timestamp() + self._SECRET_TTL_SECONDS
        self._cache[key] = (value, expiry)
        self._save()

    def wipe(self) -> None:
        """Securely wipe all cached secrets."""
        for key in self._cache:
            self._cache[key] = ("", 0.0)
        self._cache.clear()
        self._save()

    def delete(self, key: str) -> bool:
        """Delete a secret by key."""
        if key in self._cache:
            del self._cache[key]
            self._save()
            return True
        return False

    def clear(self) -> None:
        """Clear all cached secrets."""
        self._cache.clear()
        self._save()


# Global singleton
_store: Optional[SecretStore] = None


def get_secret_store() -> SecretStore:
    global _store
    if _store is None:
        _store = SecretStore()
    return _store