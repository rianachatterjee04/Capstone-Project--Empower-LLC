from __future__ import annotations
from typing import Optional
from app.core.config import settings
from cryptography.fernet import Fernet

class SecretError(Exception):
    pass

def _fernet() -> Fernet:
    if not settings.integrations_enc_key:
        raise SecretError("INTEGRATIONS_ENC_KEY missing")
    return Fernet(settings.integrations_enc_key.encode("utf-8"))

def encrypt_str(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")

def decrypt_str(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
