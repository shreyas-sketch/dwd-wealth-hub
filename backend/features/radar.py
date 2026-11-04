"""Early Coin Radar (₹5,000 plan): new listings on Binance/KuCoin and the week's trending coins,
each auto-checked with Coin X-Ray.

listing_snapshots {_id: venue, symbols, at}
radar_items {_id: "<kind>:<venue|cg>:<SYM>", symbol, name, kind new_listing|trending, venue, listed_at,
             price_usd, change_24h, xray: {label, score, red_flags}, seen_at}
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends

import market
from crypto import venue_name
import plans
from core.deps import user_dep
from core.flags import is_on
from growth import events
from growth.clock import IST, utcnow
from notify.service import alert
from state import db
from util import iso, r2, smart_round

router = APIRouter(tags=["radar"])
KEEP_DAYS = 14


async def _xray(sym: str) -> dict:
    from features.xray import run_xray
    try:
        x = await run_xray(sym)
        return {"label": x["label"], "score": x["score"], "red_flags": [f["title"] for f in x["red_flags"]][:4]}
    except Exception:  # noqa: BLE001
        return {"label": "risky", "score": 50, "red_flags": ["Couldn't check right now"]}


async def job_scan(ctx) -> dict:
    if not is_on("RADAR"):
        return {"status": "off"}
    d, now = ctx.db, ctx.now
    new = 0
    for venue in ("binance", "kucoin"):
        try:
            syms = set(await market.listings(venue))
        except Exception:  # noqa: BLE001
            continue
        snap = await d.listing_snapshots.find_one({"_id": venue})
        await d.listing_snapshots.replace_one({"_id": venue}, {"_id": venue, "symbols": sorted(syms), "at": now}, upsert=True)
        if not snap:                       # first run: remember what exists, flag nothing
            continue
        for sym in sorted(syms - set(snap.get("symbols") or [])):
            info = await market.search(sym) or {}
            await d.radar_items.update_one({"_id": f"new_listing:{venue}:{sym}"}, {"$setOnInsert": {
                "symbol": sym, "name": info.get("name") or sym, "kind": "new_listing", "venue": venue, "listed_at": now,
                "price_usd": info.get("price_usd"), "change_24h": info.get("change_24h"), "xray": await _xray(sym),
                "seen_at": now}}, upsert=True)
            new += 1
    trend = 0
    try:
        for t in await market.trending():
            sym = t["symbol"]
            await d.radar_items.update_one({"_id": f"trending:cg:{sym}"}, {
                "$set": {"price_usd": t.get("price_usd"), "change_24h": t.get("change_24h"), "seen_at": now,
                         "name": t.get("name") or sym},
                "$setOnInsert": {"symbol": sym, "kind": "trending", "venue": None, "listed_at": None,
                                 "xray": await _xray(sym), "first_seen": now}}, upsert=True)
            trend += 1
    except Exception:  # noqa: BLE001
        pass
    await d.radar_items.delete_many({"seen_at": {"$lt": now - timedelta(days=KEEP_DAYS)}})
    return {"new_listings": new, "trending": trend}


async def job_digest(ctx) -> dict:
    if not is_on("RADAR"):
        return {"status": "off"}
    d = ctx.db
    since = ctx.now - timedelta(days=1)
    rows = [r async for r in d.radar_items.find({"kind": "new_listing", "listed_at": {"$gte": since}})]
    if not rows:
        return {"sent": 0}
    text = "; ".join(f"{r['symbol']} on {venue_name(r['venue'])} ({r['xray']['label'].replace('_', ' ')})" for r in rows[:6])
    day = ctx.now.astimezone(IST).date().isoformat()
    from notify.service import alert_many           # bulk: plans resolved once, inbox written 1,000 at a time
    sent = await alert_many(d, await plans.users_with(d, "radar", ctx.now), "radar",
                            f"Coin Radar: {len(rows)} new listing{'s' if len(rows) > 1 else ''}",
                            text + ". Most new coins fall after listing — check the X-Ray before anything else.",
                            link="/app/radar", dedupe=f"radar:{day}", whatsapp=False)
    return {"sent": sent}


@router.get("/radar")
async def radar(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "radar")
    rows = [r async for r in db().radar_items.find({}).sort("seen_at", -1).limit(60)]
    merged: dict = {}                      # one card per coin and kind; venues joined ("Binance · KuCoin")
    for r in rows:
        k = (r["symbol"], r["kind"])
        if k in merged:
            v = r.get("venue")
            if v and v.lower() not in (merged[k].get("venue") or "").lower():
                merged[k]["venue"] = f'{merged[k]["venue"]} · {v}' if merged[k].get("venue") else v
        else:
            merged[k] = dict(r)
    rows = list(merged.values())
    rows.sort(key=lambda r: (r["kind"] != "new_listing", -(r.get("listed_at") or r["seen_at"]).timestamp()))
    await events.track(db(), "radar_viewed", user_id=str(user["_id"]))
    last = await db().job_runs.find_one({"name": "radar_scan"}, sort=[("at", -1)])
    return {"as_of": iso(last["at"]) if last else iso(utcnow()),
            "items": [{"id": r["_id"], "symbol": r["symbol"], "name": r.get("name"), "kind": r["kind"],
                       "venue": r.get("venue"), "listed_at": iso(r.get("listed_at")),
                       "price_usd": smart_round(r.get("price_usd")), "change_24h": r2(r.get("change_24h")),
                       "xray": r.get("xray"), "seen_at": iso(r["seen_at"])} for r in rows]}
