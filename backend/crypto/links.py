"""Linked exchanges (from Bullzeye crypto/links.py; plan gating via plans.py).

exchange_links {_id: "<uid>:<venue>", user_id, venue, sealed (envelope-encrypted key set),
  key_tail, status active|permission_failed, permissions, linked_at, verified_at, failures, failure_reason}

Rules: trade-only keys. The key's own permission flags are read at link time and re-read daily.
A key that can withdraw is refused; if a linked key fails the daily check, its key material is
WIPED (auto-unlink) and status becomes permission_failed with the reason shown in the app.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from growth import events
from growth.clock import utcnow

from . import enabled_venues, rails_enabled, vault, venue_enabled, venue_name
from .exchanges import VENUES, ExchangeError, adapter_for

MAX_FAILURES = 3


class LinkError(Exception):
    def __init__(self, code: str, msg: str, **extra):
        super().__init__(msg)
        self.detail = {"code": code, "msg": msg, **extra}


async def link(db, user: dict, venue: str, api_key: str, api_secret: str, passphrase: Optional[str] = None,
               now: Optional[datetime] = None) -> dict:
    now = now or utcnow()
    uid = str(user["_id"])
    if venue not in VENUES or not venue_enabled(venue):
        raise LinkError("bad_venue", "This exchange isn't available.")
    await events.track(db, "earn_link_started", user_id=uid, props={"venue": venue})

    async def reject(code, msg, reason, **extra):
        await events.track(db, "earn_link_rejected", user_id=uid, props={"venue": venue, "reason": reason})
        raise LinkError(code, msg, rejected_reason=reason, **extra)

    if venue == "kucoin" and not passphrase:
        await reject("passphrase", "KuCoin keys need the API passphrase too.", "no_passphrase")
    try:
        perms = await adapter_for(venue, api_key, api_secret, passphrase).permissions()
    except ExchangeError as e:
        await reject("key_invalid", "The exchange didn't accept this key. Check it was copied fully.", "key_invalid",
                     vendor=str(e)[:160])
    problems = perms.problems()
    if problems:
        await reject("key_rejected", problems[0], "withdrawal_scope" if perms.can_withdraw else
                     "no_trade" if not perms.can_trade else "no_read", problems=problems)
    doc = {"_id": f"{uid}:{venue}", "user_id": uid, "venue": venue,
           "sealed": vault.seal({"api_key": api_key, "api_secret": api_secret, "passphrase": passphrase}),
           "key_tail": vault.mask(api_key), "status": "active", "failures": 0, "failure_reason": None,
           "permissions": {"read": perms.can_read, "trade": perms.can_trade, "withdraw": perms.can_withdraw,
                           "ip_restricted": perms.ip_restricted},
           "linked_at": now, "verified_at": now, "updated_at": now}
    await db.exchange_links.replace_one({"_id": doc["_id"]}, doc, upsert=True)
    await events.track(db, "earn_link_succeeded", user_id=uid, props={"venue": venue, "ip_restricted": perms.ip_restricted})
    return public(doc)


def public(doc: dict) -> dict:
    return {"venue": doc["venue"], "key_tail": doc.get("key_tail"), "status": doc["status"],
            "linked": doc["status"] == "active", "reason": doc.get("failure_reason")}


async def adapter(db, user_id: str, venue: str):
    if not venue_enabled(venue):
        raise LinkError("venue_off", "This exchange is paused.")
    doc = await db.exchange_links.find_one({"_id": f"{user_id}:{venue}"})
    if not doc or doc["status"] != "active" or not doc.get("sealed"):
        raise LinkError("not_linked", (doc or {}).get("failure_reason") or f"Link your {venue_name(venue)} account first.")
    s = vault.open_(doc["sealed"])
    return adapter_for(venue, s["api_key"], s["api_secret"], s.get("passphrase"))


async def unlink(db, user_id: str, venue: str) -> bool:
    res = await db.exchange_links.delete_one({"_id": f"{user_id}:{venue}"})
    if res.deleted_count:
        await events.track(db, "earn_unlinked", user_id=user_id, props={"venue": venue})
    return bool(res.deleted_count)


async def fail_key(db, doc: dict, reason: str, now: datetime) -> None:
    """Auto-unlink: wipe key material, keep the row so the screen can say why."""
    await db.exchange_links.update_one({"_id": doc["_id"]}, {"$set": {
        "status": "permission_failed", "failure_reason": reason, "sealed": None, "failed_at": now}})
    await events.track(db, "earn_permission_audit_failed", user_id=doc["user_id"],
                       props={"venue": doc["venue"], "reason": reason[:120]})


async def note_venue_failure(db, doc: dict, job: str, err: str, now: datetime) -> None:
    res = await db.exchange_links.find_one_and_update(
        {"_id": doc["_id"]}, {"$inc": {"failures": 1}, "$set": {"last_error": err[:160], "last_error_at": now}},
        return_document=True)
    if res and res.get("failures") == MAX_FAILURES:
        await events.track(db, "earn_venue_call_failed", user_id=doc["user_id"],
                           props={"venue": doc["venue"], "job": job, "error": err[:120]})


async def reverify_job(ctx) -> dict:
    """Daily: re-read every key's permissions."""
    if not rails_enabled():
        return {"status": "off"}
    db, now = ctx.db, ctx.now
    ok = failed = errors = 0
    async for doc in db.exchange_links.find({"status": "active", "venue": {"$in": list(enabled_venues())}}):
        try:
            s = vault.open_(doc["sealed"])
            perms = await adapter_for(doc["venue"], s["api_key"], s["api_secret"], s.get("passphrase")).permissions()
        except ExchangeError as e:
            if e.code == "auth":
                await fail_key(db, doc, "The exchange no longer accepts this key. Link a new one.", now)
                failed += 1
            else:
                await note_venue_failure(db, doc, "reverify", str(e), now)
                errors += 1
            continue
        if perms.problems():
            await fail_key(db, doc, perms.problems()[0], now)
            failed += 1
        else:
            await db.exchange_links.update_one({"_id": doc["_id"]}, {"$set": {"verified_at": now, "failures": 0}})
            ok += 1
    return {"verified": ok, "permission_failed": failed, "errors": errors}
