"""Exchange API keys, encrypted at rest.

Envelope encryption: each key set is encrypted with a fresh Fernet data key;
the data key is wrapped by the master key. Master key source:
  EXCHANGE_VAULT_KEY  a Fernet key (Railway variable)       # NEEDS
  — move the master to a KMS (AWS KMS / GCP KMS) before public launch:
    replace wrap()/unwrap() only; stored documents don't change shape.  # NEEDS: KMS
Keys are never logged and never returned by any API (only a masked tail).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet


class VaultUnavailable(RuntimeError):
    pass


def _master() -> Fernet:
    key = os.environ.get("EXCHANGE_VAULT_KEY")
    if not key:
        if (os.environ.get("APP_ENV") or "").lower() == "production":
            raise VaultUnavailable("EXCHANGE_VAULT_KEY is not set")
        seed = (os.environ.get("JWT_SECRET") or "dev").encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(b"vault:" + seed).digest()).decode()
    return Fernet(key.encode())


def seal(secrets_: dict) -> dict:
    dk = Fernet.generate_key()
    return {"v": 1, "wrapped_key": _master().encrypt(dk).decode(),
            "blob": Fernet(dk).encrypt(json.dumps(secrets_).encode()).decode()}


def open_(sealed: dict) -> dict:
    dk = _master().decrypt(sealed["wrapped_key"].encode())
    return json.loads(Fernet(dk).decrypt(sealed["blob"].encode()))


def mask(api_key: str) -> str:
    return f"••••{api_key[-4:]}" if api_key else "—"
