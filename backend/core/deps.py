"""Shared FastAPI dependencies for the v1.0 modules.

`require_ingest_key` guards every endpoint an external cron calls (X-Ingest-Key header,
constant-time compare against INGEST_KEY).
`user_dep` / `admin_dep` resolve auth lazily so modules import without auth.py
side effects (tests override `auth.get_current_user` / `auth.require_admin`).
"""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException, Request


def verify_ingest_key(provided: Optional[str]) -> bool:
    expected = os.environ.get("INGEST_KEY", "")
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected.encode(), provided.encode())


async def require_ingest_key(x_ingest_key: Optional[str] = Header(default=None, alias="X-Ingest-Key")) -> bool:
    if not verify_ingest_key(x_ingest_key):
        raise HTTPException(status_code=401, detail="bad ingest key")
    return True


def user_dep():
    from auth import get_current_user
    return get_current_user


def admin_dep():
    from auth import require_admin
    return require_admin


async def optional_user(request: Request) -> Optional[dict]:
    try:
        from auth import get_current_user
        return await get_current_user(request)
    except Exception:  # noqa: BLE001 — anonymous is fine
        return None
