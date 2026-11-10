"""Mobile OTP login that also signs people up (adapted from Bullzeye accounts/routes.py).

POST /api/auth/otp/request  {phone, channel?}                      → {challenge_id, channel, sent_to, expires_in, resend_in, is_new, dev_code?}
POST /api/auth/otp/verify   {challenge_id, phone, code, name?, utm?, device_id?} → {user, is_new} + cookies
PATCH /api/auth/profile     {name?, email?}                         → {user}

Unlike Bullzeye, a new number gets an account on verify: webinar attendees scan the
QR, type their number, and they're in. New accounts start a trial of the ₹5,000 plan
for `trial_days` (Admin › Settings). One account per mobile number.
QA_MODE: codes go to the console sender, the code comes back as `dev_code`, and
000000 is accepted.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

import appsettings
from core.settings import settings
from growth import events
from growth.clock import utcnow

from . import otp_service
from .otp_providers import ConsoleSender, Senders, build_senders
from .phone import InvalidPhone, mask, normalise_in_mobile

log = logging.getLogger("accounts.routes")
router = APIRouter(prefix="/auth", tags=["auth-otp"])

_state: dict = {"db": None, "senders": None, "fixed": False, "wa": None}


def bind(db, senders: Optional[Senders] = None) -> None:
    _state["db"] = db
    _state["senders"] = senders
    _state["fixed"] = senders is not None


def _db():
    return _state["db"]


def _senders() -> Senders:
    from core.flags import is_on
    wa = is_on("WHATSAPP_OTP")
    if _state["senders"] is None or (not _state["fixed"] and _state["wa"] != wa):
        _state["senders"] = build_senders()
        _state["wa"] = wa
    return _state["senders"]


def client_ip(request: Request) -> str:
    for h in ("cf-connecting-ip", "x-forwarded-for"):
        v = request.headers.get(h)
        if v:
            return v.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "") or ""


class OtpRequestIn(BaseModel):
    phone: str = Field(..., max_length=20)
    channel: Literal["auto", "sms", "whatsapp"] = "auto"


class OtpVerifyIn(BaseModel):
    challenge_id: str = Field(..., max_length=64)
    phone: str = Field(..., max_length=20)
    code: str = Field(..., max_length=8)
    name: Optional[str] = Field(None, max_length=80)
    utm: dict = Field(default_factory=dict)
    device_id: Optional[str] = Field(None, max_length=128)


class ProfileIn(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    email: Optional[EmailStr] = None


_UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid", "src")
_SAFE = re.compile(r"[^A-Za-z0-9_.\-: ]")


def clean_utm(utm: dict) -> dict:
    return {k: _SAFE.sub("", str(v))[:100] for k, v in (utm or {}).items() if k in _UTM_KEYS and v}


def classify_source(utm: dict) -> str:
    """Acquisition source for Admin › Pulse. `?src=webinar` (the QR code) wins."""
    if utm.get("src"):
        return utm["src"].lower()[:30]
    if utm.get("gclid"):
        return "google_ads"
    if utm.get("fbclid"):
        return "meta_ads"
    src = (utm.get("utm_source") or "").lower()
    if src:
        return {"fb": "meta_ads", "facebook": "meta_ads", "instagram": "meta_ads", "ig": "meta_ads",
                "meta": "meta_ads", "google": "google_ads", "whatsapp": "whatsapp",
                "email": "email", "webinar": "webinar", "zoom": "webinar"}.get(src, src[:30])
    return "organic"


def admin_phones() -> set[str]:
    import os
    return {p.strip() for p in (os.environ.get("ADMIN_PHONES") or "").split(",") if p.strip()}


@router.post("/otp/request")
async def otp_request(body: OtpRequestIn, request: Request, response: Response):
    try:
        phone = normalise_in_mobile(body.phone)
    except InvalidPhone as e:
        raise HTTPException(status_code=400, detail={"code": "invalid_phone", "msg": str(e)})
    anon = events.ensure_anon_cookie(request, response)
    is_new = not await _db().users.find_one({"phone": phone}, {"_id": 1})
    senders = _senders()
    try:
        ch = await otp_service.request_otp(_db(), senders, phone, channel=body.channel,
                                           ip=client_ip(request), anon_id=anon)
    except otp_service.OtpError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    out = {"challenge_id": ch.challenge_id, "channel": ch.channel, "sent_to": mask(phone),
           "expires_in": ch.expires_in, "resend_in": ch.resend_in, "fell_back": ch.fell_back, "is_new": is_new,
           "can_sms": senders.sms is not None}
    if settings.qa_mode and not settings.is_production:
        for s in (senders.sms, senders.whatsapp):
            if isinstance(s, ConsoleSender) and s.sent and s.sent[-1][0] == phone:
                out["dev_code"] = s.sent[-1][1]
                break
    return out


async def _qa_bypass(db, challenge_id: str, phone: str, code: str) -> bool:
    if not (settings.qa_mode and not settings.is_production and code == "000000"):
        return False
    res = await db.otp_challenges.update_one({"_id": challenge_id, "phone": phone, "consumed": False},
                                             {"$set": {"consumed": True, "consumed_at": utcnow()}})
    return res.modified_count == 1


async def create_member(db, phone: str, *, name: Optional[str], utm: dict, role: str = "user") -> dict:
    now = utcnow()
    trial_days = (await appsettings.get(db))["trial_days"]
    doc = {"phone": phone, "phone_verified_at": now, "name": (name or "").strip() or None, "role": role,
           "status": "active", "created_at": now, "first_login_at": now,
           "trial_ends_at": now + timedelta(days=trial_days) if trial_days else None,
           "acquisition": {"source": classify_source(utm), "utm": utm, "at": now}}
    try:
        res = await db.users.insert_one(doc)
        doc["_id"] = res.inserted_id
    except Exception:  # noqa: BLE001 — two verifies racing on one number
        return await db.users.find_one({"phone": phone})
    await events.track(db, "signup", user_id=str(doc["_id"]), props={"source": doc["acquisition"]["source"]})
    return doc


@router.post("/otp/verify")
async def otp_verify(body: OtpVerifyIn, request: Request, response: Response):
    from auth import public_user, set_auth_cookies
    db = _db()
    try:
        phone = normalise_in_mobile(body.phone)
    except InvalidPhone as e:
        raise HTTPException(status_code=400, detail={"code": "invalid_phone", "msg": str(e)})
    anon = events.anon_id_from(request)
    if not await _qa_bypass(db, body.challenge_id, phone, body.code.strip()):
        try:
            await otp_service.verify_otp(db, body.challenge_id, phone, body.code, anon_id=anon)
        except otp_service.OtpError as e:
            raise HTTPException(status_code=e.status, detail=e.detail)

    now = utcnow()
    user = await db.users.find_one({"phone": phone})
    is_new = user is None
    role = "admin" if phone in admin_phones() else "user"
    if is_new:
        user = await create_member(db, phone, name=body.name, utm=clean_utm(body.utm), role=role)
    else:
        if (user.get("status") or "active") == "revoked":
            raise HTTPException(status_code=403, detail={"code": "revoked", "msg": "This account is disabled."})
        upd: dict = {"last_login_at": now}
        if role == "admin" and user.get("role") != "admin":
            upd["role"] = "admin"
        if body.name and not user.get("name"):
            upd["name"] = body.name.strip()
        await db.users.update_one({"_id": user["_id"]}, {"$set": upd})
        user.update(upd)
        await events.track(db, "login", user_id=str(user["_id"]))
    if body.device_id:
        await db.users.update_one({"_id": user["_id"]}, {"$addToSet": {"device_ids": body.device_id[:128]}})
    await events.identify(db, anon, str(user["_id"]))
    set_auth_cookies(response, str(user["_id"]), user.get("role") or "user")
    return {"user": public_user(user), "is_new": is_new}


def _user_dep():
    from auth import get_current_user
    return get_current_user


@router.patch("/profile")
async def update_profile(body: ProfileIn, user: dict = Depends(_user_dep())):
    from auth import public_user
    upd = {}
    if body.name is not None:
        upd["name"] = body.name.strip() or None
    if body.email is not None:
        email = body.email.lower().strip()
        clash = await _db().users.find_one({"email": email, "_id": {"$ne": user["_id"]}})
        if clash:
            raise HTTPException(status_code=409, detail={"code": "email_taken", "msg": "Email already in use."})
        upd["email"] = email
    if upd:
        await _db().users.update_one({"_id": user["_id"]}, {"$set": upd})
    return {"user": public_user({**user, **upd})}
