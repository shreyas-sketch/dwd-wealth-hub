"""P2P Rate Finder (₹5,000 plan): live USDT buy rates in INR on Binance and KuCoin P2P, with a
safety score per merchant. Cached for 5 minutes.

# NEEDS verify: both P2P endpoints below are the ones the exchanges' own web pages call; they are
# not documented public APIs and can change or block server traffic. If they do, set P2P_MODE=off
# (the screen then says "rates unavailable") until a supported source is chosen.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

import plans
from core.deps import user_dep
from core.flags import is_on
from core.vendors import vendor_mode
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

router = APIRouter(tags=["p2p"])
_cache: dict = {}
TTL = 300
BINANCE_P2P = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
KUCOIN_P2P = "https://www.kucoin.com/_api/otc/ad/list"

TIPS = [
    "Buy only from merchants with 98%+ completion and hundreds of orders.",
    "Pay only through the exchange's order screen, and only the exact amount, from your own bank account.",
    "Never mark 'paid' before you've actually paid, and never release or chat outside the exchange.",
    "Prefer UPI/IMPS from an account in your own name; keep screenshots until the coins arrive.",
    "If the price is much better than everyone else's, skip it — it's often bait.",
    "Very large one-time P2P buys from unknown merchants carry bank-freeze risk; spread buys across trusted merchants.",
]


def safety(completion_pct: float, orders: int) -> str:
    if completion_pct >= 98 and orders >= 500:
        return "high"
    if completion_pct >= 95 and orders >= 100:
        return "medium"
    return "low"


def _fake(amount: float) -> list[dict]:
    from market.fake import _rng
    from growth.clock import IST
    r = _rng("p2p", utcnow().astimezone(IST).strftime("%Y-%m-%d-%H"))
    out = []
    for venue, base in (("binance", 91.6), ("kucoin", 91.9)):
        offers = []
        for i in range(6):
            comp = round(r.uniform(91, 100), 1)
            orders = r.choice([45, 120, 380, 870, 1500, 4200, 9800])
            offers.append({"merchant": f"{['Crypto', 'Swift', 'Bharat', 'Rapid', 'Trusty', 'Prime'][i]}{r.randint(10, 99)}",
                           "price": round(base + i * 0.12 + r.uniform(0, 0.25), 2), "min_inr": r.choice([500, 1000, 2000]),
                           "max_inr": r.choice([50000, 100000, 250000, 500000]), "completion_pct": comp, "orders": orders,
                           "payment": r.sample(["UPI", "IMPS", "Bank Transfer", "Paytm"], 2),
                           "safety": safety(comp, orders)})
        offers = [o for o in offers if o["min_inr"] <= amount <= o["max_inr"]] or offers
        offers.sort(key=lambda o: o["price"])
        out.append({"venue": venue, "best_price": offers[0]["price"], "offers": offers[:5]})
    return out


async def _binance(amount: float, c: httpx.AsyncClient) -> Optional[dict]:
    body = {"asset": "USDT", "fiat": "INR", "tradeType": "BUY", "page": 1, "rows": 10, "transAmount": str(int(amount)),
            "payTypes": [], "publisherType": None}
    r = await c.post(BINANCE_P2P, json=body, headers={"content-type": "application/json"})
    offers = []
    for it in (r.json().get("data") or [])[:10]:
        adv, ad = it.get("adv") or {}, it.get("advertiser") or {}
        comp = float(ad.get("monthFinishRate") or 0) * 100
        orders = int(ad.get("monthOrderCount") or 0)
        offers.append({"merchant": ad.get("nickName"), "price": float(adv.get("price") or 0),
                       "min_inr": float(adv.get("minSingleTransAmount") or 0),
                       "max_inr": float(adv.get("dynamicMaxSingleTransAmount") or adv.get("maxSingleTransAmount") or 0),
                       "completion_pct": round(comp, 1), "orders": orders,
                       "payment": [t.get("tradeMethodName") for t in adv.get("tradeMethods") or []][:3],
                       "safety": safety(comp, orders)})
    offers = [o for o in offers if o["price"] > 0]
    return {"venue": "binance", "best_price": min(o["price"] for o in offers), "offers": offers[:5]} if offers else None


async def _kucoin(amount: float, c: httpx.AsyncClient) -> Optional[dict]:
    r = await c.get(KUCOIN_P2P, params={"status": "PUTUP", "currency": "USDT", "legal": "INR", "side": "SELL",
                                        "page": 1, "pageSize": 10, "amount": int(amount)})
    offers = []
    for it in (r.json().get("items") or [])[:10]:
        comp = float(it.get("completeRate") or it.get("dealRate") or 0)
        comp = comp * 100 if comp <= 1 else comp
        orders = int(it.get("dealOrderNum") or it.get("totalOrderNum") or 0)
        offers.append({"merchant": it.get("nickName"), "price": float(it.get("floatPrice") or it.get("price") or 0),
                       "min_inr": float(it.get("limitMinQuote") or 0), "max_inr": float(it.get("limitMaxQuote") or 0),
                       "completion_pct": round(comp, 1), "orders": orders,
                       "payment": [p.get("payTypeCode") for p in it.get("adPayTypes") or []][:3],
                       "safety": safety(comp, orders)})
    offers = [o for o in offers if o["price"] > 0]
    return {"venue": "kucoin", "best_price": min(o["price"] for o in offers), "offers": offers[:5]} if offers else None


async def rates(amount: float) -> dict:
    mode = vendor_mode("p2p")
    if mode == "off" or not is_on("P2P"):
        raise HTTPException(status_code=503, detail={"code": "off", "msg": "P2P rates are unavailable right now."})
    key = f"{mode}:{int(amount // 1000)}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    if mode == "fake":
        venues = _fake(amount)
    else:
        venues = []
        async with httpx.AsyncClient(timeout=12, headers={"user-agent": "Mozilla/5.0"}) as c:
            for fn in (_binance, _kucoin):
                try:
                    v = await fn(amount, c)
                    if v:
                        venues.append(v)
                except Exception:  # noqa: BLE001 — one venue down shouldn't hide the other
                    continue
        if not venues:
            raise HTTPException(status_code=503, detail={"code": "unavailable", "msg": "P2P rates couldn't be loaded. Try again shortly."})
    out = {"asset": "USDT", "fiat": "INR", "as_of": iso(utcnow()), "venues": venues, "tips": TIPS}
    _cache[key] = (time.time(), out)
    return out


@router.get("/p2p")
async def p2p(amount_inr: float = Query(5000, ge=100, le=10_000_000), user: dict = Depends(user_dep())):
    await plans.require(db(), user, "p2p")
    await events.track(db(), "p2p_viewed", user_id=str(user["_id"]))
    return await rates(amount_inr)
