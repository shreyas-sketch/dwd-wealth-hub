"""Inbox alerts.

    inbox {_id, user_id, kind, title, body, link, at, read, dedupe}

`alert()` writes one row (deduped by `dedupe` when given) and, when the WHATSAPP_ALERTS
flag is on and AiSensy is configured, sends the same text on WhatsApp (quiet hours
22:00–08:00 IST: inbox only).

Kinds: verdict_changed, crash, radar, event, autopilot, basket_change, airdrop, system
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends

from core.deps import user_dep
from growth import events
from growth.clock import IST, utcnow
from util import iso

from .channels import build_whatsapp

log = logging.getLogger("notify")
KINDS = {"verdict_changed", "crash", "radar", "event", "autopilot", "basket_change", "airdrop", "system", "picks"}
_state = {"db": None, "wa": None, "wa_built": False}


def bind(db) -> None:
    _state["db"] = db


def _wa():
    if not _state["wa_built"]:
        _state["wa"], _state["wa_built"] = build_whatsapp(), True
    return _state["wa"]


def _quiet(now) -> bool:
    h = now.astimezone(IST).hour
    return h >= 22 or h < 8


async def alert(db, user_id: str, kind: str, title: str, body: str, link: Optional[str] = None,
                dedupe: Optional[str] = None, whatsapp: bool = True) -> Optional[str]:
    if kind not in KINDS:
        raise ValueError(kind)
    now = utcnow()
    _id = f"{user_id}:{dedupe}" if dedupe else uuid.uuid4().hex
    row = {"_id": _id, "user_id": user_id, "kind": kind, "title": title[:140], "body": body[:600],
           "link": link, "at": now, "read": False}
    try:
        await db.inbox.insert_one(row)
    except Exception as e:  # noqa: BLE001 — duplicate dedupe
        if "duplicate" in str(e).lower():
            return None
        raise
    await events.track(db, "message_sent", user_id=user_id, props={"kind": kind})
    from core.flags import is_on
    if whatsapp and is_on("WHATSAPP_ALERTS") and not _quiet(now) and _wa() is not None:
        try:
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            if user:
                res = await _wa().send(user, row)
                await db.inbox.update_one({"_id": _id}, {"$set": {"wa": {"ok": res.ok, "error": res.error}}})
        except Exception:  # noqa: BLE001
            log.warning("whatsapp alert failed", exc_info=True)
    return _id


async def alert_many(db, user_ids: list[str], kind: str, title: str, body: str, link: Optional[str] = None,
                     dedupe: Optional[str] = None, whatsapp: bool = True) -> int:
    """The same alert to many members in bulk (crash coach, radar digest, event reminders): inbox rows and
    events go in with insert_many, 1,000 at a time, instead of 2–3 writes per member. Dedupe works as in
    alert(): a member who already has `<uid>:<dedupe>` is skipped. Returns how many new rows were written."""
    if kind not in KINDS:
        raise ValueError(kind)
    from pymongo.errors import BulkWriteError
    now = utcnow()
    written: list[str] = []
    for k in range(0, len(user_ids), 1000):
        chunk = user_ids[k:k + 1000]
        rows = [{"_id": f"{u}:{dedupe}" if dedupe else uuid.uuid4().hex, "user_id": u, "kind": kind,
                 "title": title[:140], "body": body[:600], "link": link, "at": now, "read": False} for u in chunk]
        try:
            await db.inbox.insert_many(rows, ordered=False)
            ok = rows
        except BulkWriteError as e:
            errs = e.details.get("writeErrors", [])
            if any(x.get("code") != 11000 for x in errs):
                raise
            bad = {x["index"] for x in errs}
            ok = [r for i, r in enumerate(rows) if i not in bad]
        if ok:
            await db.events.insert_many([{"_id": uuid.uuid4().hex, "name": "message_sent", "ts": now,
                                          "user_id": r["user_id"], "anon_id": None, "props": {"kind": kind},
                                          "src": "server"} for r in ok], ordered=False)
        written += [r["user_id"] for r in ok]
    from core.flags import is_on
    if whatsapp and written and is_on("WHATSAPP_ALERTS") and not _quiet(now) and _wa() is not None:
        import asyncio
        sem = asyncio.Semaphore(10)                         # gentle on AiSensy

        async def one(u: dict):
            async with sem:
                try:
                    res = await _wa().send(u, {"title": title, "body": body, "link": link, "kind": kind})
                    await db.inbox.update_one({"_id": f"{u['_id']}:{dedupe}" if dedupe else None},
                                              {"$set": {"wa": {"ok": res.ok, "error": res.error}}})
                except Exception:  # noqa: BLE001
                    log.warning("whatsapp alert failed", exc_info=True)
        for k in range(0, len(written), 1000):
            users = [u async for u in db.users.find({"_id": {"$in": [ObjectId(x) for x in written[k:k + 1000]]}})]
            await asyncio.gather(*(one(u) for u in users))
    return len(written)


def _row(d: dict) -> dict:
    return {"id": d["_id"], "kind": d["kind"], "title": d["title"], "body": d["body"], "link": d.get("link"),
            "at": iso(d["at"]), "read": bool(d.get("read"))}


router = APIRouter(tags=["inbox"])


@router.get("/inbox")
async def inbox(user: dict = Depends(user_dep())):
    db = _state["db"]
    uid = str(user["_id"])
    rows = [_row(d) async for d in db.inbox.find({"user_id": uid}).sort("at", -1).limit(60)]
    unread = await db.inbox.count_documents({"user_id": uid, "read": False})
    return {"unread": unread, "items": rows}


@router.post("/inbox/read-all")
async def read_all(user: dict = Depends(user_dep())):
    await _state["db"].inbox.update_many({"user_id": str(user["_id"]), "read": False}, {"$set": {"read": True}})
    return {"ok": True}
