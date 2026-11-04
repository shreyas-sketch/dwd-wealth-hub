"""Sessions: JWT in httpOnly cookies (from Bullzeye auth.py, trimmed).

Members log in by mobile OTP (accounts/routes.py). Staff log in with email +
password (`POST /api/auth/staff/login`); the first staff admin is seeded from
ADMIN_EMAIL / ADMIN_PASSWORD on startup. Owner phones in ADMIN_PHONES get the
admin role on OTP login.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

log = logging.getLogger("auth")

JWT_ALGORITHM = "HS256"
ACCESS_TTL_MIN = 60 * 12
REFRESH_TTL_DAYS = 30
LOCKOUT_MAX_ATTEMPTS = 5
LOCKOUT_WINDOW_MIN = 15


def _jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return False


def create_access_token(user_id: str, role: str) -> str:
    return jwt.encode({"sub": user_id, "role": role, "type": "access",
                       "exp": _now() + timedelta(minutes=ACCESS_TTL_MIN)}, _jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "type": "refresh", "exp": _now() + timedelta(days=REFRESH_TTL_DAYS)},
                      _jwt_secret(), algorithm=JWT_ALGORITHM)


def _cookie_kwargs() -> dict:
    from core.settings import settings
    kw = dict(httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, path="/")
    if settings.cookie_domain:
        kw["domain"] = settings.cookie_domain
    return kw


def set_auth_cookies(response: Response, user_id: str, role: str) -> str:
    access, refresh = create_access_token(user_id, role), create_refresh_token(user_id)
    kw = _cookie_kwargs()
    response.set_cookie("access_token", access, max_age=ACCESS_TTL_MIN * 60, **kw)
    response.set_cookie("refresh_token", refresh, max_age=REFRESH_TTL_DAYS * 86400, **kw)
    return access


def clear_auth_cookies(response: Response) -> None:
    kw = _cookie_kwargs()
    response.delete_cookie("access_token", path="/", domain=kw.get("domain"))
    response.delete_cookie("refresh_token", path="/", domain=kw.get("domain"))


def iso(v):
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v


def public_user(doc: dict) -> dict:
    return {"id": str(doc["_id"]), "phone": doc.get("phone"), "name": doc.get("name"), "email": doc.get("email"),
            "role": doc.get("role") or "user", "created_at": iso(doc.get("created_at"))}


router = APIRouter(prefix="/auth", tags=["auth"])
_db_ref = {"db": None}


def bind_db(db) -> None:
    _db_ref["db"] = db


def _db():
    if _db_ref["db"] is None:
        raise RuntimeError("Auth module not bound to a database")
    return _db_ref["db"]


async def _user_from_token(token: str, kind: str = "access") -> dict:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"code": "expired", "msg": "Session expired. Log in again."})
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail={"code": "invalid_token", "msg": "Log in again."})
    if payload.get("type") != kind:
        raise HTTPException(status_code=401, detail={"code": "invalid_token", "msg": "Log in again."})
    try:
        user = await _db().users.find_one({"_id": ObjectId(payload["sub"])})
    except Exception:  # noqa: BLE001
        user = None
    if not user:
        raise HTTPException(status_code=401, detail={"code": "no_user", "msg": "Log in again."})
    if (user.get("status") or "active") == "revoked":
        raise HTTPException(status_code=403, detail={"code": "revoked", "msg": "This account is disabled."})
    return user


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        h = request.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            token = h[7:]
    if not token:
        raise HTTPException(status_code=401, detail={"code": "not_logged_in", "msg": "Log in to continue."})
    return await _user_from_token(token)


async def optional_user(request: Request) -> Optional[dict]:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if (user.get("role") or "user") != "admin":
        raise HTTPException(status_code=403, detail={"code": "admin_only", "msg": "Admin only."})
    return user


class StaffLoginIn(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    import plans
    return {"user": public_user(user), "plan": await plans.plan_info(_db(), user)}


@router.get("/session")
async def session(request: Request, response: Response):
    """Session probe for the web app: always 200, never 401.

    {user, plan} when logged in. When the access cookie has expired but the refresh cookie is still good, the
    session is renewed here (new cookies), saving the 401 → /refresh → retry round trip. Logged out:
    {user: null, plan: null, reason: null | "expired" | "revoked"}. Public pages call this on every load, so
    a logged-out visitor no longer logs a 401 in the console (QA 3 Nov). `/auth/me` keeps its 401 contract."""
    import plans
    response.headers["Cache-Control"] = "no-store"

    async def ok(user: dict) -> dict:
        return {"user": public_user(user), "plan": await plans.plan_info(_db(), user), "reason": None}

    def out(reason: Optional[str]) -> dict:
        if request.cookies.get("access_token") or request.cookies.get("refresh_token"):
            clear_auth_cookies(response)
        return {"user": None, "plan": None, "reason": reason}

    access = request.cookies.get("access_token")
    if not access:
        h = request.headers.get("Authorization", "")
        access = h[7:] if h.startswith("Bearer ") else None
    for token, kind in ((access, "access"), (request.cookies.get("refresh_token"), "refresh")):
        if not token:
            continue
        try:
            user = await _user_from_token(token, kind)
        except HTTPException as e:
            if e.status_code == 403:
                return out("revoked")
            continue
        if kind == "refresh":
            set_auth_cookies(response, str(user["_id"]), user.get("role") or "user")
        return await ok(user)
    return out("expired" if (access or request.cookies.get("refresh_token")) else None)


@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail={"code": "not_logged_in", "msg": "Log in to continue."})
    user = await _user_from_token(token, "refresh")
    set_auth_cookies(response, str(user["_id"]), user.get("role") or "user")
    return {"ok": True}


async def _lockout_ok(identifier: str) -> bool:
    doc = await _db().login_attempts.find_one({"_id": identifier})
    if not doc:
        return True
    from growth.clock import as_utc
    if doc.get("count", 0) >= LOCKOUT_MAX_ATTEMPTS and _now() - as_utc(doc["first_at"]) < timedelta(minutes=LOCKOUT_WINDOW_MIN):
        return False
    if _now() - as_utc(doc["first_at"]) >= timedelta(minutes=LOCKOUT_WINDOW_MIN):
        await _db().login_attempts.delete_one({"_id": identifier})
    return True


@router.post("/staff/login")
async def staff_login(body: StaffLoginIn, response: Response):
    email = body.email.strip().lower()
    if not await _lockout_ok(email):
        raise HTTPException(status_code=429, detail={"code": "locked_out", "msg": "Too many tries. Wait 15 minutes."})
    user = await _db().users.find_one({"email": email, "password_hash": {"$exists": True}})
    if not user or not verify_password(body.password, user["password_hash"]):
        await _db().login_attempts.update_one({"_id": email}, {"$inc": {"count": 1}, "$setOnInsert": {"first_at": _now()}},
                                              upsert=True)
        raise HTTPException(status_code=401, detail={"code": "bad_login", "msg": "Wrong email or password."})
    if (user.get("status") or "active") == "revoked":
        raise HTTPException(status_code=403, detail={"code": "revoked", "msg": "This account is disabled."})
    await _db().login_attempts.delete_one({"_id": email})
    await _db().users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": _now()}})
    set_auth_cookies(response, str(user["_id"]), user.get("role") or "user")
    from growth import events
    await events.track(_db(), "staff_login", user_id=str(user["_id"]))
    return {"user": public_user(user)}


async def seed_admin(db) -> None:
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or ""
    if not email or not password:
        return
    existing = await db.users.find_one({"email": email})
    if existing:
        if existing.get("role") != "admin":
            await db.users.update_one({"_id": existing["_id"]}, {"$set": {"role": "admin"}})
        if not existing.get("password_hash"):
            await db.users.update_one({"_id": existing["_id"]}, {"$set": {"password_hash": hash_password(password)}})
        return
    await db.users.insert_one({"email": email, "name": "Admin", "role": "admin", "status": "active",
                               "password_hash": hash_password(password), "created_at": _now(),
                               "acquisition": {"source": "staff"}})
    log.info("Seeded staff admin %s", email)
