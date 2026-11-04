"""Serve the built React app from FastAPI (one origin, one Railway service).

Order matters: call mount_spa(app) AFTER every API/public router is included,
because the catch-all route below answers anything left unmatched.

Paths under /api
are never answered with index.html — they 404 as JSON if nothing matched, so a
typo in an API path cannot silently return HTML.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .settings import settings

log = logging.getLogger("core.spa")

SERVER_PREFIXES = ("/api",)

_FALLBACK_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>App</title></head>
<body style="font-family:sans-serif;padding:40px">API is running. Frontend build not found.</body></html>"""


class _ImmutableStatic(StaticFiles):
    """Hashed CRA assets — cache for a year."""

    async def get_response(self, path, scope):  # type: ignore[override]
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


def _safe_file(build_dir: Path, rel: str) -> Path | None:
    try:
        candidate = (build_dir / rel.lstrip("/")).resolve()
    except (OSError, ValueError):
        return None
    if build_dir not in candidate.parents and candidate != build_dir:
        return None
    return candidate if candidate.is_file() else None


def mount_spa(app: FastAPI, build_dir: Path | None = None) -> None:
    build_dir = (build_dir or settings.frontend_build_dir).resolve()
    index = build_dir / "index.html"
    has_build = index.is_file()
    if has_build and (build_dir / "static").is_dir():
        app.mount("/static", _ImmutableStatic(directory=build_dir / "static"), name="static")
    else:
        log.warning("Frontend build not found at %s — serving API only", build_dir)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_catch_all(full_path: str, request: Request):
        path = "/" + full_path
        if path.startswith(SERVER_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")
        if not has_build:
            return HTMLResponse(_FALLBACK_HTML)
        f = _safe_file(build_dir, full_path) if full_path else None
        if f is not None and f.name != "index.html":
            return FileResponse(f)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
