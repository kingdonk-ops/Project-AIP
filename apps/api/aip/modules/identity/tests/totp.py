"""RFC 6238 TOTP for tests only (Keycloak computes and checks the real ones; ADR 0005)."""

import hashlib
import hmac
import struct
import time


def totp(secret: bytes, *, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    counter = int((time.time() if at is None else at) // step)
    mac = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % 10**digits
    return str(code).zfill(digits)
