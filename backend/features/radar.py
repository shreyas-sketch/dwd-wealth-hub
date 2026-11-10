"""Early Coin Radar (₹5,000 plan): new listings on Binance/KuCoin and the week's trending coins,
each auto-checked with Coin X-Ray.

listing_snapshots {_id: venue, symbols, at}
radar_items {_id: "<kind>:<venue|cg>:<SYM>", symbol, name, kind new_listing|trending, venue, listed_at,
             price_usd, change_24h, xray: {label, score, red_flags}, seen_at}

A check that couldn't run (data source busy or down) is stored as label "unchecked" with no score and retried on the
next scan. It is never shown as "Risky" (QA 10 Nov: BTC and SOL appeared as Risky 50 because checks had failed).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

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


log = logging.getLogger("radar")
UNCHECKED = {"label": "unchecked", "score": None, "red_flags": []}


async def _xray(sym: str) -> dict:
    from features.xray import cached_xray
    try:
        x = await cached_xray(sym)
        return {"label": x["label"], "score": x["score"], "red_flags": [f["title"] for f in x["red_flags"]][:4]}
    except Exception as e:  # noqa: BLE001 — retried on the next scan
        log.warning("radar X-Ray for %s failed: %s", sym, getattr(e, "detail", None) or e)
        return dict(UNCHECKED)


async def _xray_if_needed(d, _id: str, sym: str) -> Optional[dict]:
    """X-Ray a coin the first time it appears, or again if its last check couldn't run."""
    prev = await d.radar_items.find_one({"_id": _id}, {"xray": 1})
    if prev and (prev.get("xray") or {}).get("label") not in (None, "unchecked"):
        return None
    return await _xray(sym)


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
            try:
                info = await market.search(sym) or {}
            except Exception:  # noqa: BLE001 — name and price fill in on a later scan
                info = {}
            _id = f"new_listing:{venue}:{sym}"
            await d.radar_items.update_one({"_id": _id}, {"$setOnInsert": {
                "symbol": sym, "name": info.get("name") or sym, "kind": "new_listing", "venue": venue, "listed_at": now,
                "price_usd": info.get("price_usd"), "change_24h": info.get("change_24h"), "xray": await _xray(sym),
                "seen_at": now}}, upsert=True)
            new += 1
    trend = 0
    try:
        for t in await market.trending():
            sym = t["symbol"]
            _id = f"trending:cg:{sym}"
            x = await _xray_if_needed(d, _id, sym)
            await d.radar_items.update_one({"_id": _id}, {
                "$set": {"price_usd": t.get("price_usd"), "change_24h": t.get("change_24h"), "seen_at": now,
                         "name": t.get("name") or sym, **({"xray": x} if x else {})},
                "$setOnInsert": {"symbol": sym, "kind": "trending", "venue": None, "listed_at": None, "first_seen": now}},
                upsert=True)
            trend += 1
    except Exception:  # noqa: BLE001
        pass
    # Retry any coin whose check couldn't run last time (old-style failures are converted first).
    from maintenance import fix_legacy_radar_checks
    await fix_legacy_radar_checks(d)
    rechecked = 0
    async for r in d.radar_items.find({"xray.label": "unchecked"}, {"symbol": 1}).limit(25):
        x = await _xray(r["symbol"])
        if x["label"] != "unchecked":
            await d.radar_items.update_one({"_id": r["_id"]}, {"$set": {"xray": x}})
            rechecked += 1
    await d.radar_items.delete_many({"seen_at": {"$lt": now - timedelta(days=KEEP_DAYS)}})
    unchecked = await d.radar_items.count_documents({"xray.label": "unchecked"})
    return {"new_listings": new, "trending": trend, "rechecked": rechecked, "unchecked": unchecked}


async def job_digest(ctx) -> dict:
    if not is_on("RADAR"):
        return {"status": "off"}
    d = ctx.db
    since = ctx.now - timedelta(days=1)
    rows = [r async for r in d.radar_items.find({"kind": "new_listing", "listed_at": {"$gte": since}})]
    if not rows:
        return {"sent": 0}
    labels = {"safe": "looks safe", "risky": "risky", "likely_scam": "likely scam", "unchecked": "not checked yet"}
    text = "; ".join(f"{r['symbol']} on {venue_name(r['venue'])} ({labels.get((r.get('xray') or {}).get('label'), 'not checked yet')})"
                     for r in rows[:6])
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
