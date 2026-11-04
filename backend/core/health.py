"""Liveness and readiness probes.

GET /api/health        → process is up (Railway healthcheck; no DB call).
GET /api/health/ready  → Mongo reachable; 503 otherwise.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .settings import settings

router = APIRouter(prefix="/health", tags=["health"])
_db = None


def bind_db(db) -> None:
    global _db
    _db = db


@router.get("")
async def health():
    return {"ok": True, "env": settings.env, "release": settings.release,
            "time": datetime.now(timezone.utc).isoformat()}


@router.get("/ready")
async def ready():
    if _db is None:
        return JSONResponse({"ok": False, "mongo": "unbound"}, status_code=503)
    try:
        await _db.command("ping")
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "mongo": type(e).__name__}, status_code=503)
    return {"ok": True, "mongo": "ok"}
