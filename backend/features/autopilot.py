"""SIP Autopilot screens: link KuCoin/Binance (trade-only key), set up coin plans, see buys.

₹2,000 plan: BTC, monthly. ₹5,000 plan: BTC/ETH/SOL/XRP, weekly or monthly (plans.AUTOPILOT).
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import market
import plans
from core.deps import user_dep
from crypto import dca, enabled_venues, links, rails_enabled, venue_name
from crypto.exchanges import VENUES, ExchangeError
from crypto.fx import usd_inr
from growth import events
from growth.clock import utcnow
from state import db

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


class LinkIn(BaseModel):
    venue: Literal["kucoin", "binance"]
    api_key: str = Field(..., min_length=8, max_length=200)
    api_secret: str = Field(..., min_length=8, max_length=200)
    passphrase: Optional[str] = Field(None, max_length=200)


class PlanIn(BaseModel):
    venue: Literal["kucoin", "binance"]
    coin: str = Field(..., max_length=10)
    amount_inr: float = Field(..., ge=1000, le=1_000_000)
    frequency: Literal["weekly", "monthly"] = "monthly"
    weekday: int = Field(0, ge=0, le=6)
    day: int = Field(1, ge=1, le=28)


def _http(e: Exception) -> HTTPException:
    if isinstance(e, links.LinkError):
        return HTTPException(status_code=400, detail=e.detail)
    return HTTPException(status_code=400, detail={"code": getattr(e, "code", "exchange_error"), "msg": str(e)})


def _lite_only() -> HTTPException:
    """403 locked, worded for a ₹2,000 member who already has Autopilot (just not this coin or weekly)."""
    e = plans.locked_error("autopilot", "pro")
    e.detail["msg"] = "On the ₹2,000 plan Autopilot buys Bitcoin once a month. ETH, SOL, XRP and weekly buys are in the ₹5,000 plan."
    return e


async def _gate(user: dict) -> str:
    plan = await plans.require(db(), user, "autopilot")
    if not rails_enabled():
        raise HTTPException(status_code=503, detail={"code": "off", "msg": "Autopilot is paused right now."})
    return plan


async def state_for(user: dict) -> dict:
    uid = str(user["_id"])
    plan = (await plans.effective_plan(db(), user))["plan"]
    rows = {d["venue"]: d async for d in db().exchange_links.find({"user_id": uid})}
    venues = []
    for v in VENUES:
        d = rows.get(v)
        venues.append({"venue": v, "linked": bool(d and d["status"] == "active"), "key_tail": (d or {}).get("key_tail"),
                       "status": (d or {}).get("status", "not_linked"), "reason": (d or {}).get("failure_reason"),
                       "available": v in enabled_venues()})
    syms = set()
    async for b in db().dca_buys.find({"user_id": uid}, {"coin": 1}):
        syms.add(b["coin"])
    px = {s: v["price_usd"] for s, v in (await market.prices(list(syms))).items()} if syms else {}
    fx, _ = await usd_inr(db())
    return {"enabled": rails_enabled(), "venues": venues, "plans": await dca.summary(db(), uid, px, fx),
            "allowed": plans.AUTOPILOT[plan], "min_inr": dca.MIN_INR_PER_COIN}


@router.get("")
async def get_state(user: dict = Depends(user_dep())):
    return await state_for(user)


@router.post("/link")
async def link(body: LinkIn, user: dict = Depends(user_dep())):
    await _gate(user)
    try:
        return await links.link(db(), user, body.venue, body.api_key.strip(), body.api_secret.strip(),
                                (body.passphrase or "").strip() or None)
    except links.LinkError as e:
        raise _http(e)


@router.delete("/link/{venue}")
async def unlink(venue: str, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    await links.unlink(db(), uid, venue)
    await db().dca_plans.update_many({"user_id": uid, "venue": venue}, {"$set": {"status": "paused",
                                                                                 "last_error": "Exchange unlinked"}})
    return {"ok": True}


@router.get("/balance/{venue}")
async def balance(venue: str, user: dict = Depends(user_dep())):
    try:
        ad = await links.adapter(db(), str(user["_id"]), venue)
        bal = await ad.balances()
    except (links.LinkError, ExchangeError) as e:
        raise _http(e)
    fx, _ = await usd_inr(db())
    usdt = float(bal.get("USDT", 0.0))
    return {"usdt": round(usdt, 2), "inr_est": round(usdt * fx, 2)}


async def save_plan(user: dict, *, kind: str, venue: str, amount_inr: float, frequency: str, weekday: int, day: int,
                    coin: Optional[str] = None, basket: Optional[dict] = None) -> dict:
    uid = str(user["_id"])
    if not await db().exchange_links.find_one({"_id": f"{uid}:{venue}", "status": "active"}):
        raise HTTPException(status_code=400, detail={"code": "not_linked", "msg": f"Link your {venue_name(venue)} account first."})
    now = utcnow()
    p = {"_id": uuid.uuid4().hex[:16], "user_id": uid, "kind": kind, "venue": venue, "coin": coin,
         "basket_id": basket["_id"] if basket else None, "basket_name": basket["name"] if basket else None,
         "amount_inr": amount_inr, "frequency": frequency, "weekday": weekday, "day": day, "status": "active",
         "created_at": now, "updated_at": now, "last_error": None}
    p["next_at"] = dca.next_run(p, now)
    await db().dca_plans.insert_one(p)
    await events.track(db(), "dca_plan_saved", user_id=uid, props={"kind": kind, "frequency": frequency})
    return next(x for x in (await state_for(user))["plans"] if x["id"] == p["_id"])


@router.post("/plan")
async def create_plan(body: PlanIn, user: dict = Depends(user_dep())):
    plan = await _gate(user)
    allowed = plans.AUTOPILOT[plan]
    coin = body.coin.upper()
    if coin not in allowed["coins"]:
        raise _lite_only() if plan == "lite" else HTTPException(
            status_code=400, detail={"code": "bad_coin", "msg": f"Autopilot runs on {', '.join(allowed['coins'])}."})
    if body.frequency not in allowed["frequencies"]:
        raise _lite_only()
    if body.venue not in enabled_venues():
        raise HTTPException(status_code=400, detail={"code": "bad_venue", "msg": "This exchange isn't available."})
    return await save_plan(user, kind="coin", venue=body.venue, amount_inr=body.amount_inr, frequency=body.frequency,
                           weekday=body.weekday, day=body.day, coin=coin)


async def _own(plan_id: str, user: dict) -> dict:
    p = await db().dca_plans.find_one({"_id": plan_id, "user_id": str(user["_id"])})
    if not p:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Plan not found."})
    return p


@router.post("/plan/{plan_id}/pause")
async def pause(plan_id: str, user: dict = Depends(user_dep())):
    await _own(plan_id, user)
    await db().dca_plans.update_one({"_id": plan_id}, {"$set": {"status": "paused"}})
    return next(x for x in (await state_for(user))["plans"] if x["id"] == plan_id)


@router.post("/plan/{plan_id}/resume")
async def resume(plan_id: str, user: dict = Depends(user_dep())):
    await _gate(user)
    p = await _own(plan_id, user)
    await db().dca_plans.update_one({"_id": plan_id}, {"$set": {"status": "active", "last_error": None,
                                                                "next_at": dca.next_run(p, utcnow())}})
    return next(x for x in (await state_for(user))["plans"] if x["id"] == plan_id)


@router.delete("/plan/{plan_id}")
async def delete_plan(plan_id: str, user: dict = Depends(user_dep())):
    await _own(plan_id, user)
    await db().dca_plans.delete_one({"_id": plan_id})
    return {"ok": True}


async def job_buys(ctx) -> dict:
    return await dca.run_job(ctx)


async def job_reverify(ctx) -> dict:
    return await links.reverify_job(ctx)
