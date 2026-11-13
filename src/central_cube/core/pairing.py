"""One-time pairing code primitives. Codes are stored as salted hashes."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time


class PairingCode:
    def __init__(self, ttl_seconds: int = 300) -> None:
        if ttl_seconds < 30 or ttl_seconds > 900:
            raise ValueError("Pairing code TTL must be between 30 and 900 seconds")
        self.ttl_seconds = ttl_seconds
        self._salt = secrets.token_bytes(16)
        self._code = f"{secrets.randbelow(1_000_000):06d}"
        self._digest = hashlib.scrypt(self._code.encode(), salt=self._salt, n=2**14, r=8, p=1)
        self._expires_at = time.monotonic() + ttl_seconds
        self._used = False
        self._attempts = 0
        self._max_attempts = 5

    @property
    def display_code(self) -> str:
        if self._used or time.monotonic() >= self._expires_at:
            raise RuntimeError("Pairing code is no longer available")
        return self._code

    def verify_once(self, candidate: str) -> bool:
        if self._used or time.monotonic() >= self._expires_at:
            return False
        self._attempts += 1
        if not isinstance(candidate, str) or len(candidate) != 6 or not candidate.isdigit():
            if self._attempts >= self._max_attempts:
                self._used = True
                self._code = ""
            return False
        digest = hashlib.scrypt(candidate.encode(), salt=self._salt, n=2**14, r=8, p=1)
        valid = hmac.compare_digest(self._digest, digest)
        if valid:
            self._used = True
            self._code = ""
        elif self._attempts >= self._max_attempts:
            self._used = True
            self._code = ""
        return valid
