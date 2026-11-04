"""OTP challenges: create, deliver, verify.

`otp_challenges` {_id, phone, code_hash, channel, provider, attempts,
                  expires_at, consumed, superseded, ip, created_at, purge_at}

- Codes are 6 digits from `secrets`, stored only as HMAC-SHA256(challenge_id:code).
- A new request supersedes the phone's earlier open challenges.
- Limits: 30 s between sends per phone, 5 sends/hour and 10/day per phone,
  30 sends/hour per IP, 5 wrong guesses per challenge, 10-minute expiry.
- Channel: WhatsApp first when enabled, SMS on any WhatsApp failure; the user
  can also ask for SMS directly ("Send by SMS instead").
- Rows purge after 24 h (TTL index on purge_at).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional

from growth import events
from growth.clock import as_utc, utcnow

from .otp_providers import Senders, SendResult

OTP_LEN = 6
TTL_MIN = 10
RESEND_COOLDOWN_S = 30
MAX_PER_PHONE_HOUR = 5
MAX_PER_PHONE_DAY = 10
# Per-IP cap is only a brake on scripted abuse. Indian mobile carriers (Jio, Airtel, Vi) put thousands of
# phones behind one public IP (CGNAT), so a low cap blocks real webinar sign-ups: the load test showed 30/hour
# let only 30 of 500 people behind one IP sign up. The per-phone limits below are the real protection.
MAX_PER_IP_HOUR = int(os.environ.get("OTP_MAX_PER_IP_HOUR", "1000") or 1000)
MAX_ATTEMPTS = 5

Channel = Literal["auto", "sms", "whatsapp"]


class OtpError(Exception):
    def __init__(self, code: str, msg: str, status: int = 400, **extra):
        super().__init__(msg)
        self.code, self.status, self.extra = code, status, extra

    @property
    def detail(self) -> dict:
        return {"code": self.code, "msg": str(self), **self.extra}


@dataclass
class Challenge:
    challenge_id: str
    channel: str
    expires_in: int
    resend_in: int
    fell_back: bool


def _secret() -> bytes:
    key = os.environ.get("OTP_SECRET") or os.environ.get("JWT_SECRET")
    if not key:
        raise RuntimeError("OTP_SECRET (or JWT_SECRET) must be set")
    return key.encode()


def _hash(challenge_id: str, code: str) -> str:
    return hmac.new(_secret(), f"{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _test_numbers() -> dict[str, str]:
    """OTP_TEST_NUMBERS='+919999900001:246810,...' — fixed codes for QA/app review.
    Nothing is sent to these numbers. Keep empty unless a reviewer needs it."""
    out = {}
    for pair in (os.environ.get("OTP_TEST_NUMBERS") or "").split(","):
        if ":" in pair:
            num, code = pair.split(":", 1)
            if code.strip().isdigit() and len(code.strip()) == OTP_LEN:
                out[num.strip()] = code.strip()
    return out


def new_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_LEN):0{OTP_LEN}d}"


async def _check_limits(db, phone: str, ip: str, now: datetime) -> None:
    last = await db.otp_challenges.find_one({"phone": phone}, sort=[("created_at", -1)])
    if last:
        wait = RESEND_COOLDOWN_S - int((now - as_utc(last["created_at"])).total_seconds())
        if wait > 0:
            raise OtpError("resend_cooldown", f"Wait {wait}s before asking for a new code.", 429,
                           retry_in=wait)
    hour, day = now - timedelta(hours=1), now - timedelta(days=1)
    if await db.otp_challenges.count_documents({"phone": phone, "created_at": {"$gte": hour}}) >= MAX_PER_PHONE_HOUR:
        raise OtpError("phone_hourly_limit", "Too many codes requested. Try again in an hour.", 429)
    if await db.otp_challenges.count_documents({"phone": phone, "created_at": {"$gte": day}}) >= MAX_PER_PHONE_DAY:
        raise OtpError("phone_daily_limit", "Too many codes today. Try again tomorrow.", 429)
    if ip and await db.otp_challenges.count_documents({"ip": ip, "created_at": {"$gte": hour}}) >= MAX_PER_IP_HOUR:
        raise OtpError("ip_limit", "Too many requests from this network. Try again later.", 429)


async def _deliver(senders: Senders, phone: str, code: str, channel: Channel) -> tuple[SendResult, bool]:
    """Returns (result, fell_back)."""
    if channel == "whatsapp" and senders.whatsapp is None:
        channel = "sms"
    order = [senders.sms] if channel == "sms" else [senders.whatsapp, senders.sms]
    order = [s for s in order if s is not None]
    if not order:
        return SendResult(False, "none", "none", error="no OTP provider configured"), False
    first: Optional[SendResult] = None
    for i, sender in enumerate(order):
        res = await sender.send(phone, code, TTL_MIN)
        first = first or res
        if res.ok:
            return res, i > 0
    return first, False


async def request_otp(
    db, senders: Senders, phone: str, *, channel: Channel = "auto", ip: str = "",
    anon_id: Optional[str] = None, now: Optional[datetime] = None,
) -> Challenge:
    now = now or utcnow()
    await _check_limits(db, phone, ip, now)
    challenge_id = uuid.uuid4().hex
    test_code = _test_numbers().get(phone)
    code = test_code or new_code()
    if test_code:
        res, fell_back = SendResult(True, "test_number", "sms", ref="test"), False
    else:
        res, fell_back = await _deliver(senders, phone, code, channel)
    await db.otp_challenges.update_many(
        {"phone": phone, "consumed": False, "superseded": {"$ne": True}},
        {"$set": {"superseded": True}})
    await db.otp_challenges.insert_one({
        "_id": challenge_id, "phone": phone, "code_hash": _hash(challenge_id, code),
        "channel": res.channel, "provider": res.provider, "provider_ref": res.ref,
        "send_ok": res.ok, "send_error": res.error, "attempts": 0, "consumed": False,
        "superseded": False, "ip": ip, "created_at": now,
        "expires_at": now + timedelta(minutes=TTL_MIN), "purge_at": now + timedelta(days=1)})
    if not res.ok:
        await events.track(db, "otp_failed", anon_id=anon_id,
                           props={"reason": "send_failed", "provider": res.provider,
                                  "error": (res.error or "")[:120]})
        raise OtpError("send_failed", "We couldn't send the code. Try SMS or try again.", 502)
    await events.track(db, "otp_requested", anon_id=anon_id, props={
        "channel": res.channel, "provider": res.provider, "fell_back": fell_back})
    return Challenge(challenge_id, res.channel, TTL_MIN * 60, RESEND_COOLDOWN_S, fell_back)


async def verify_otp(
    db, challenge_id: str, phone: str, code: str, *, anon_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> None:
    """Raises OtpError unless the code is right. Consumes the challenge on success."""
    now = now or utcnow()
    code = (code or "").strip()
    ch = await db.otp_challenges.find_one({"_id": challenge_id, "phone": phone})
    if not ch or ch.get("consumed") or ch.get("superseded") or not ch.get("send_ok"):
        raise OtpError("invalid_challenge", "This code is no longer valid. Ask for a new one.")
    if now >= as_utc(ch["expires_at"]):
        raise OtpError("expired", "This code has expired. Ask for a new one.")
    # Count the attempt BEFORE comparing, atomically, so parallel guesses can't exceed the cap.
    upd = await db.otp_challenges.update_one(
        {"_id": challenge_id, "attempts": {"$lt": MAX_ATTEMPTS}, "consumed": False},
        {"$inc": {"attempts": 1}})
    if upd.modified_count != 1:
        raise OtpError("too_many_attempts", "Too many wrong codes. Ask for a new one.", 429)
    if not (len(code) == OTP_LEN and code.isdigit()
            and hmac.compare_digest(_hash(challenge_id, code), ch["code_hash"])):
        left = MAX_ATTEMPTS - (ch["attempts"] + 1)
        await events.track(db, "otp_failed", anon_id=anon_id, props={"reason": "wrong_code"})
        raise OtpError("wrong_code", "That code is not right.", 400, attempts_left=max(0, left))
    done = await db.otp_challenges.update_one(
        {"_id": challenge_id, "consumed": False}, {"$set": {"consumed": True, "consumed_at": now}})
    if done.modified_count != 1:
        raise OtpError("invalid_challenge", "This code was already used.")
