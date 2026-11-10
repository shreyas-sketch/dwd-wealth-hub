"""Crypto Baskets (₹5,000 plan): themed mixes of coins the team builds. Practice in Paper Money,
buy once on your own exchange, or put the basket on Autopilot.

baskets {_id, name, theme, description, coins: [{symbol, weight_pct}], risk_note, change_note, changed_at,
         active, created_at}

Rules: minimum ₹1,000 per coin per buy (so min_inr = the larger of 1,000 × coins and the amount that gives the
smallest-weight coin ₹1,000); coins must be listed on both
Binance and KuCoin; not enough USDT → nothing is bought; the software never sells. A basket change
alerts everyone holding it ("X removed — open the app to decide").

auto_rule (optional): "top5" keeps the basket on the five largest coins listed on both exchanges, weights 35/20/15/15/15
by size. The weekly job `baskets_auto` acts on the first Monday of the month (or on "Run now"); a coin is only
swapped out once it drops below 7th, so the basket doesn't churn on small moves.
"""
from __future__ import annotations

import math
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import market
import plans
from core.deps import user_dep
from core.flags import is_on
from crypto import dca, enabled_venues, links
from crypto.exchanges import ExchangeError
from growth import events
from growth.clock import utcnow
from notify.service import alert
from state import db
from util import iso

router = APIRouter(prefix="/baskets", tags=["baskets"])


class CoinW(BaseModel):
    symbol: str = Field(..., max_length=15)
    weight_pct: float = Field(..., gt=0, le=100)


class BasketIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    theme: Optional[str] = Field(None, max_length=60)
    description: Optional[str] = Field(None, max_length=600)
    coins: list[CoinW] = Field(..., min_length=1, max_length=8)
    risk_note: Optional[str] = Field(None, max_length=300)
    change_note: Optional[str] = Field(None, max_length=300)
    active: bool = True
    auto_rule: Optional[Literal["top5"]] = None


class AmountIn(BaseModel):
    amount_inr: float = Field(..., ge=1000, le=10_000_000)


class InvestIn(BaseModel):
    venue: Literal["kucoin", "binance"]
    amount_inr: float = Field(..., ge=1000, le=10_000_000)


class AutoIn(InvestIn):
    frequency: Literal["weekly", "monthly"] = "monthly"
    weekday: int = Field(0, ge=0, le=6)
    day: int = Field(1, ge=1, le=28)


def min_inr(coins: list[dict]) -> float:
    """The smallest buy _split() accepts: every coin, including the smallest weight, gets ₹1,000. QA 11 Nov: the
    card showed 1,000 × coins (₹2,000 for BTC 60 / ETH 40) and a buy of that amount was refused (needs ₹2,500)."""
    if not coins:
        return 0.0
    lowest = min(c["weight_pct"] for c in coins)
    return float(max(dca.MIN_INR_PER_COIN * len(coins), math.ceil(dca.MIN_INR_PER_COIN * 100 / lowest)))


def public(b: dict) -> dict:
    return {"id": b["_id"], "name": b["name"], "theme": b.get("theme"), "description": b.get("description"),
            "coins": b["coins"], "min_inr": min_inr(b["coins"]), "risk_note": b.get("risk_note"),
            "change_note": b.get("change_note"), "changed_at": iso(b.get("changed_at")), "active": b.get("active", True),
            "auto_rule": b.get("auto_rule")}


async def _basket(bid: str) -> dict:
    b = await db().baskets.find_one({"_id": bid, "active": {"$ne": False}})
    if not b:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Basket not found."})
    return b


def _split(b: dict, amount: float) -> dict[str, float]:
    need = dca.MIN_INR_PER_COIN * len(b["coins"])
    split = {c["symbol"]: amount * c["weight_pct"] / 100 for c in b["coins"]}
    if amount < need or min(split.values()) < dca.MIN_INR_PER_COIN - 0.01:
        lowest = min(c["weight_pct"] for c in b["coins"])
        need = max(need, dca.MIN_INR_PER_COIN * 100 / lowest)
        raise HTTPException(status_code=400, detail={"code": "too_small",
                            "msg": f"This basket needs at least ₹{need:,.0f} so every coin gets ₹1,000."})
    return split


@router.get("")
async def listing(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "baskets")
    return {"items": [public(b) async for b in db().baskets.find({"active": {"$ne": False}}).sort("created_at", 1)]}


@router.post("/{basket_id}/practice")
async def practice(basket_id: str, body: AmountIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "baskets")
    b = await _basket(basket_id)
    from features.paper import buy_many, view
    doc = await buy_many(user, _split(b, body.amount_inr), note=f"basket {b['name']}")
    await events.track(db(), "basket_practice", user_id=str(user["_id"]), props={"basket": b["name"]})
    return await view(user, doc)


@router.post("/{basket_id}/invest")
async def invest(basket_id: str, body: InvestIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "baskets")
    if not is_on("BASKET_INVEST") or body.venue not in enabled_venues():
        raise HTTPException(status_code=503, detail={"code": "off", "msg": "Real-money basket buys are paused. Practice works."})
    b = await _basket(basket_id)
    amounts = _split(b, body.amount_inr)
    now = utcnow()
    try:
        rows = await dca.execute(db(), str(user["_id"]), body.venue, amounts, ref=f"basket{uuid.uuid4().hex[:8]}",
                                 now=now, note=f"Basket {b['name']}")
    except links.LinkError as e:
        raise HTTPException(status_code=400, detail=e.detail)
    except ExchangeError as e:
        status = 409 if e.code == "short_usdt" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "msg": str(e)})
    await db().basket_holders.update_one({"_id": f"{user['_id']}:{basket_id}"},
                                         {"$set": {"user_id": str(user["_id"]), "basket_id": basket_id, "at": now}}, upsert=True)
    await events.track(db(), "basket_invest", user_id=str(user["_id"]),
                       props={"basket": b["name"], "total_inr": round(body.amount_inr)})
    return {"orders": rows, "total_inr": round(sum(r["inr"] for r in rows if r["status"] == "filled"), 2)}


@router.post("/{basket_id}/autopilot")
async def autopilot(basket_id: str, body: AutoIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "baskets")
    plan = await plans.require(db(), user, "autopilot")
    if body.frequency not in plans.AUTOPILOT[plan]["frequencies"]:
        raise plans.locked_error("autopilot", "pro")
    b = await _basket(basket_id)
    _split(b, body.amount_inr)
    from features.autopilot import save_plan
    out = await save_plan(user, kind="basket", venue=body.venue, amount_inr=body.amount_inr, frequency=body.frequency,
                          weekday=body.weekday, day=body.day, basket=b)
    await db().basket_holders.update_one({"_id": f"{user['_id']}:{basket_id}"},
                                         {"$set": {"user_id": str(user["_id"]), "basket_id": basket_id, "at": utcnow()}},
                                         upsert=True)
    return out


# ---------------------------------------------------------------- admin helpers ----
async def validate(body: BasketIn) -> list[dict]:
    coins = [{"symbol": c.symbol.upper().strip(), "weight_pct": round(c.weight_pct, 2)} for c in body.coins]
    if len({c["symbol"] for c in coins}) != len(coins):
        raise HTTPException(status_code=400, detail={"code": "dupe", "msg": "Each coin once."})
    total = sum(c["weight_pct"] for c in coins)
    if abs(total - 100) > 0.5:
        raise HTTPException(status_code=400, detail={"code": "weights", "msg": f"Weights add up to {total:g}%, not 100%."})
    try:
        both = set(await market.listings("binance")) & set(await market.listings("kucoin"))
    except Exception:  # noqa: BLE001
        both = None
    if both is not None:
        missing = [c["symbol"] for c in coins if c["symbol"] not in both]
        if missing:
            raise HTTPException(status_code=400, detail={"code": "not_listed",
                                "msg": f"Not listed on both Binance and KuCoin: {', '.join(missing)}."})
    return coins


async def save(body: BasketIn, basket_id: Optional[str] = None) -> dict:
    coins = await validate(body)
    now = utcnow()
    doc = {**body.model_dump(exclude={"coins"}), "coins": coins}
    if basket_id:
        old = await db().baskets.find_one({"_id": basket_id})
        if not old:
            raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Basket not found."})
        if "auto_rule" not in body.model_fields_set:      # a client that leaves it out (older admin page, API call) keeps what was set
            doc["auto_rule"] = old.get("auto_rule")
        changed = {c["symbol"]: c["weight_pct"] for c in old["coins"]} != {c["symbol"]: c["weight_pct"] for c in coins}
        if changed:
            doc["changed_at"] = now
            removed = sorted({c["symbol"] for c in old["coins"]} - {c["symbol"] for c in coins})
            added = sorted({c["symbol"] for c in coins} - {c["symbol"] for c in old["coins"]})
            text = (body.change_note or "") or (
                (f"Removed {', '.join(removed)}. " if removed else "") + (f"Added {', '.join(added)}. " if added else "") +
                "Weights updated.")
            doc["change_note"] = text.strip()
            msg = (f"{text.strip()} New money now goes into the new mix. "
                   + (f"If you hold {', '.join(removed)} from this basket, open the app to decide — we never sell for you."
                      if removed else ""))
            async for h in db().basket_holders.find({"basket_id": basket_id}):
                await alert(db(), h["user_id"], "basket_change", f"Basket changed: {old['name']}", msg,
                            link="/app/baskets", dedupe=f"bc:{basket_id}:{now.isoformat()[:16]}")
        await db().baskets.update_one({"_id": basket_id}, {"$set": doc})
        return public(await db().baskets.find_one({"_id": basket_id}))
    doc.update(_id=uuid.uuid4().hex[:10], created_at=now, changed_at=now)
    await db().baskets.insert_one(doc)
    return public(doc)


# ---------------------------------------------------------------- automatic refresh ----
TOP5_WEIGHTS = (35.0, 20.0, 15.0, 15.0, 15.0)
TOP5_KEEP_RANK = 7          # a current coin stays while it is in the top 7, so small moves don't swap coins


async def top5_mix(current: list[str]) -> Optional[list[dict]]:
    """The "top5" rule: the five largest coins listed on BOTH Binance and KuCoin, weighted by size. Current coins
    that are still in the top 7 keep their place. None when the market data or listings can't be read."""
    try:
        both = set(await market.listings("binance")) & set(await market.listings("kucoin"))
        rows = await market.top_coins(25, exclude_stables=True, tradable=False)
    except Exception:  # noqa: BLE001
        return None
    from features.xray import is_meme             # a meme coin never enters a rule basket, even in the top 5
    ranked = [r["symbol"] for r in rows if r["symbol"] in both and not is_meme(r)]
    if len(ranked) < 5:
        return None
    keep = [s for s in ranked[:TOP5_KEEP_RANK] if s in current]
    pick = (keep + [s for s in ranked if s not in keep])[:5]
    pick.sort(key=ranked.index)                   # biggest first gets the biggest weight
    return [{"symbol": s, "weight_pct": w} for s, w in zip(pick, TOP5_WEIGHTS)]


async def job_auto_refresh(ctx) -> dict:
    """Weekly; acts on the first Monday of the month (days 1–7), or any day from "Run now"."""
    if not is_on("BASKET_AUTO"):
        return {"status": "off"}
    from growth.clock import IST, as_utc
    if not ctx.manual and as_utc(ctx.now).astimezone(IST).day > 7:
        return {"status": "not_this_week"}
    out = []
    async for b in ctx.db.baskets.find({"auto_rule": "top5", "active": {"$ne": False}}):
        cur = [c["symbol"] for c in b["coins"]]
        mix = await top5_mix(cur)
        if mix is None:
            out.append({"basket": b["name"], "status": "no_data"})
            continue
        if {c["symbol"]: c["weight_pct"] for c in mix} == {c["symbol"]: c["weight_pct"] for c in b["coins"]}:
            out.append({"basket": b["name"], "status": "unchanged"})
            continue
        body = BasketIn(name=b["name"], theme=b.get("theme"), description=b.get("description"),
                        coins=[CoinW(**c) for c in mix], risk_note=b.get("risk_note"), change_note=None,
                        active=True, auto_rule="top5")
        try:
            await save(body, b["_id"])            # alerts every holder with what was removed / added
        except HTTPException as e:
            out.append({"basket": b["name"], "status": "rejected", "why": str(e.detail)[:160]})
            continue
        out.append({"basket": b["name"], "status": "changed", "coins": [c["symbol"] for c in mix]})
    return {"status": "ok", "baskets": out}
