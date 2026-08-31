from __future__ import annotations
from typing import Optional, Tuple
import hmac, hashlib, base64

def verify_hmac_sha256(raw_body: bytes, secret: str, signature: str) -> bool:
    # Accept hex or base64 signatures; compare in constant time.
    mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    sig = signature.strip()
    try:
        if all(c in "0123456789abcdefABCDEF" for c in sig) and len(sig) in (64, 128):
            expected = mac.hex()
            return hmac.compare_digest(expected.lower(), sig.lower())
    except Exception:
        pass
    try:
        expected_b64 = base64.b64encode(mac).decode("utf-8")
        return hmac.compare_digest(expected_b64, sig)
    except Exception:
        return False
