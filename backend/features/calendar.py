"""Crypto Events Calendar (₹5,000 plan): token unlocks, listings, upgrades, the halving, macro dates
and ETF decisions — flagged "yours" when a coin is in the member's watchlist, plan or holdings, with a
day-before alert.

crypto_events {_id, date (YYYY-MM-DD), title, kind unlock|listing|upgrade|halving|macro|etf, coins, impact high|medium|low,
               note, source manual|seed|unlocks, created_at}

Token unlocks can be pulled from a vendor (# NEEDS: TOKEN_UNLOCKS_API_KEY + endpoint confirmation);
until then the team adds them in Admin › Events.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import plans
from core.deps import user_dep
from growth import events
from growth.clock import IST, utcnow
from notify.service import alert
from state import db

router = APIRouter(tags=["calendar"])
KINDS = ("unlock", "listing", "upgrade", "halving", "macro", "etf")

SEED = [
    ("2028-04-15", "Bitcoin halving (estimated)", "halving", ["BTC"], "high",
     "New BTC supply per block halves. The exact date depends on block times."),
]


class EventIn(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    title: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(..., pattern="^(unlock|listing|upgrade|halving|macro|etf)$")
    coins: list[str] = Field(default_factory=list, max_length=10)
    impact: str = Field("medium", pattern="^(high|medium|low)$")
    note: Optional[str] = Field(None, max_length=400)


async def user_coins(d, user: dict) -> set[str]:
    uid = str(user["_id"])
    out = set(((await d.watchlists.find_one({"_id": uid})) or {}).get("symbols") or [])
    async for p in d.crypto_plans.find({"user_id": uid}):
        out |= {a["symbol"] for a in p.get("allocation", [])}
    async for b in d.dca_buys.find({"user_id": uid}, {"coin": 1}):
        out.add(b["coin"])
    paper = await d.paper.find_one({"_id": uid})
    out |= set((paper or {}).get("positions", {}).keys())
    out.discard("USDT")
    return out


def public(e: dict, mine: set[str]) -> dict:
    return {"id": e["_id"], "date": e["date"], "title": e["title"], "kind": e["kind"], "coins": e.get("coins") or [],
            "impact": e.get("impact", "medium"), "note": e.get("note"), "yours": bool(set(e.get("coins") or []) & mine)}


async def ensure_seed(d) -> None:
    for dt, title, kind, coins, impact, note in SEED:
        await d.crypto_events.update_one({"_id": f"seed:{kind}:{dt}"}, {"$setOnInsert": {
            "date": dt, "title": title, "kind": kind, "coins": coins, "impact": impact, "note": note, "source": "seed",
            "created_at": utcnow()}}, upsert=True)


@router.get("/calendar")
async def calendar(days: int = Query(60, ge=1, le=400), user: dict = Depends(user_dep())):
    await plans.require(db(), user, "calendar")
    today = utcnow().astimezone(IST).date()
    end = today + timedelta(days=days)
    mine = await user_coins(db(), user)
    rows = [e async for e in db().crypto_events.find({"date": {"$gte": today.isoformat(), "$lte": end.isoformat()}}).sort("date", 1)]
    if not any(r["kind"] == "halving" for r in rows):          # always show the next halving at the end
        nxt = await db().crypto_events.find_one({"kind": "halving", "date": {"$gte": today.isoformat()}}, sort=[("date", 1)])
        if nxt:
            rows.append(nxt)
    await events.track(db(), "calendar_viewed", user_id=str(user["_id"]))
    return {"items": [public(e, mine) for e in rows]}


async def save(body: EventIn, event_id: Optional[str] = None) -> dict:
    try:
        date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "bad_date", "msg": f"{body.date} isn't a real date."})
    doc = {**body.model_dump(), "coins": [c.upper().strip() for c in body.coins if c.strip()]}
    if event_id:
        res = await db().crypto_events.update_one({"_id": event_id}, {"$set": doc})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Event not found."})
        return public(await db().crypto_events.find_one({"_id": event_id}), set())
    doc.update(_id=uuid.uuid4().hex[:10], source="manual", created_at=utcnow())
    await db().crypto_events.insert_one(doc)
    return public(doc, set())


async def job_alerts(ctx) -> dict:
    d = ctx.db
    tomorrow = (ctx.now.astimezone(IST).date() + timedelta(days=1)).isoformat()
    evs = [e async for e in d.crypto_events.find({"date": tomorrow})]
    if not evs:
        return {"sent": 0}
    from notify.service import alert_many
    eligible = set(await plans.users_with(d, "calendar", ctx.now))
    sent = 0
    for e in evs:                                   # bulk per event: who follows its coins, found with 4 queries
        coins = [c for c in (e.get("coins") or []) if c != "USDT"]
        followers: dict[str, set] = {}
        if coins:
            async for w in d.watchlists.find({"symbols": {"$in": coins}}, {"symbols": 1}):
                followers.setdefault(w["_id"], set()).update(set(w["symbols"]) & set(coins))
            async for p in d.crypto_plans.find({"allocation.symbol": {"$in": coins}}, {"user_id": 1, "allocation": 1}):
                followers.setdefault(p["user_id"], set()).update({a["symbol"] for a in p["allocation"]} & set(coins))
            async for b in d.dca_buys.find({"coin": {"$in": coins}}, {"user_id": 1, "coin": 1}):
                followers.setdefault(b["user_id"], set()).add(b["coin"])
            for c in coins:
                async for pp in d.paper.find({f"positions.{c}": {"$exists": True}}, {"_id": 1}):
                    followers.setdefault(pp["_id"], set()).add(c)
        title, note = f"Tomorrow: {e['title']}", e.get("note") or ""
        by_text: dict[str, list[str]] = {}
        for uid in eligible:
            hit = followers.get(uid)
            if hit or e.get("impact") == "high":
                by_text.setdefault(note + (f" You follow {', '.join(sorted(hit))}." if hit else ""), []).append(uid)
        for text, uids in by_text.items():
            sent += await alert_many(d, uids, "event", title, text, link="/app/calendar", dedupe=f"ev:{e['_id']}",
                                     whatsapp=False)
    return {"sent": sent, "events": len(evs)}
