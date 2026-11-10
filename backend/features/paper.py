"""Paper Money: ₹1,00,000 of practice money, started from a crypto plan (or a basket).

paper {_id: uid, start_inr, cash_inr, positions: {SYM: {qty, cost_inr}}, plan_id, plan_split {SYM: pct} (the
       plan's split when started or last rebalanced), started_at, trades: [...]}
paper_history {_id: "<uid>:<date>", user_id, date, value_inr}
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import market
import plans
from core.deps import user_dep
from crypto.fx import usd_inr
from growth import events
from growth.clock import IST, utcnow
from state import db
from util import iso, smart_round

router = APIRouter(tags=["paper"])
START_INR = 100_000.0
# Coins Paper Money can trade, in the order the trade form lists them (sent to the form as `tradable`).
TRADABLE_ORDER = ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "TRX", "LINK", "AVAX", "SUI", "TON", "DOT", "LTC",
                  "NEAR", "SHIB", "PEPE", "WIF", "BONK", "FLOKI")
TRADABLE = set(TRADABLE_ORDER)


class TradeIn(BaseModel):
    symbol: str = Field(..., max_length=15)
    side: Literal["buy", "sell"]
    amount_inr: float = Field(..., gt=0, le=10_000_000)


class StartIn(BaseModel):
    plan_id: str = Field(..., max_length=64)


async def _prices_inr(syms: list[str]) -> dict[str, float]:
    if not syms:
        return {}
    fx, _ = await usd_inr(db())
    px = await market.prices(syms)
    return {s: px[s]["price_usd"] * fx for s in syms if s in px and px[s].get("price_usd")}


async def view(user: dict, doc: Optional[dict] = None) -> dict:
    uid = str(user["_id"])
    doc = doc or await db().paper.find_one({"_id": uid})
    can_trade = plans.plan_allows((await plans.effective_plan(db(), user))["plan"], "paper_trade")
    if not doc:
        return {"start_inr": START_INR, "cash_inr": START_INR, "value_inr": START_INR, "pnl_inr": 0.0, "pnl_pct": 0.0,
                "positions": [], "history": [], "plan_id": None, "can_trade": can_trade, "started_at": None,
                "tradable": list(TRADABLE_ORDER)}
    pos = doc.get("positions") or {}
    px = await _prices_inr(list(pos))
    rows, total = [], doc["cash_inr"]
    for s, p in sorted(pos.items()):
        price = px.get(s, 0.0)
        val = p["qty"] * price
        total += val
        avg = p["cost_inr"] / p["qty"] if p["qty"] else 0
        rows.append({"symbol": s, "qty": p["qty"], "avg_price_inr": smart_round(avg), "price_inr": smart_round(price),
                     "value_inr": round(val, 2), "pnl_pct": round((price / avg - 1) * 100, 2) if avg else 0.0})
    hist = [{"date": h["date"], "value_inr": round(h["value_inr"], 2)}
            async for h in db().paper_history.find({"user_id": uid}).sort("date", 1).limit(400)]
    today = utcnow().astimezone(IST).date().isoformat()
    if not hist or hist[-1]["date"] != today:
        hist.append({"date": today, "value_inr": round(total, 2)})
    start = doc.get("start_inr", START_INR)
    return {"start_inr": start, "cash_inr": round(doc["cash_inr"], 2), "value_inr": round(total, 2),
            "pnl_inr": round(total - start, 2), "pnl_pct": round((total / start - 1) * 100, 2),
            "positions": rows, "history": hist, "plan_id": doc.get("plan_id"), "can_trade": can_trade, "tradable": list(TRADABLE_ORDER),
            "started_at": iso(doc.get("started_at")), "plan_drift": await _plan_drift(uid, doc)}


async def _plan_drift(uid: str, doc: dict) -> Optional[dict]:
    """When the plan this practice money was started from now has different coins (the member edited it, e.g.
    Moderate → Safe), say so, so the screen can offer to rebalance. Trades the member made on purpose are never
    undone without asking (QA 10 Nov: Paper Money kept SOL and XRP after the plan changed to BTC/ETH/USDT)."""
    if not doc.get("plan_id"):
        return None
    plan = await db().crypto_plans.find_one({"_id": doc["plan_id"], "user_id": uid}, {"allocation": 1, "goal_name": 1})
    if not plan:
        return None
    want = {a["symbol"] for a in plan["allocation"] if a["symbol"] != "USDT" and a["pct"] > 0}
    have = {s for s, p in (doc.get("positions") or {}).items() if p.get("qty", 0) > 0}
    # Only a change to the plan counts, not the member's own trades (QA 10 Nov: buying DOGE by hand said the plan
    # "is now 40% BTC…" though the plan never changed). The split is saved when Paper Money starts or rebalances.
    saved = doc.get("plan_split")
    if saved is not None:
        if saved == split_of(plan):
            return None
    elif not (want - have):                # started before the split was saved: only flag coins the plan added
        return None
    return {"plan_id": plan["_id"], "goal_name": plan.get("goal_name"),
            "plan_split": [{"symbol": a["symbol"], "pct": a["pct"]} for a in plan["allocation"]],
            "not_in_plan": sorted(have - want), "missing": sorted(want - have)}


def split_of(plan: dict) -> dict[str, float]:
    return {a["symbol"]: a["pct"] for a in plan.get("allocation") or [] if a.get("pct")}


async def buy_many(user: dict, amounts_inr: dict[str, float], *, plan_id: Optional[str] = None, fresh: bool = False,
                   note: str = "") -> dict:
    """Buy several coins at live prices (used by plan start and basket practice)."""
    uid = str(user["_id"])
    now = utcnow()
    doc = None if fresh else await db().paper.find_one({"_id": uid})
    if not doc:
        doc = {"_id": uid, "start_inr": START_INR, "cash_inr": START_INR, "positions": {}, "plan_id": plan_id,
               "started_at": now, "trades": []}
    total = sum(amounts_inr.values())
    if total > doc["cash_inr"] + 0.01:
        raise HTTPException(status_code=400, detail={"code": "not_enough_cash",
                                                     "msg": f"Not enough practice cash (₹{doc['cash_inr']:,.0f} left)."})
    px = await _prices_inr([s for s in amounts_inr if s != "USDT"])
    for s, amt in amounts_inr.items():
        if s == "USDT" or amt <= 0:
            continue
        if s not in px:
            raise HTTPException(status_code=400, detail={"code": "no_price", "msg": f"No price for {s} right now."})
        p = doc["positions"].setdefault(s, {"qty": 0.0, "cost_inr": 0.0})
        p["qty"] += amt / px[s]
        p["cost_inr"] += amt
        doc["cash_inr"] -= amt
        doc["trades"] = (doc.get("trades") or [])[-199:] + [{"at": now, "symbol": s, "side": "buy", "inr": amt,
                                                              "price_inr": px[s], "note": note}]
    if plan_id:
        doc["plan_id"] = plan_id
    await db().paper.replace_one({"_id": uid}, doc, upsert=True)
    return doc


@router.get("/paper")
async def get_paper(user: dict = Depends(user_dep())):
    return await view(user)


@router.post("/paper/start")
async def start(body: StartIn, user: dict = Depends(user_dep())):
    plan = await db().crypto_plans.find_one({"_id": body.plan_id, "user_id": str(user["_id"])})
    if not plan:
        raise HTTPException(status_code=404, detail={"code": "no_plan", "msg": "Make a plan first."})
    # 90% goes in by the plan's mix; ₹10,000 stays as cash so the first practice trade works.
    amounts = {a["symbol"]: START_INR * 0.9 * a["pct"] / 100 for a in plan["allocation"]}
    doc = await buy_many(user, amounts, plan_id=body.plan_id, fresh=True, note="plan start")
    doc["plan_split"] = split_of(plan)
    await db().paper.update_one({"_id": doc["_id"]}, {"$set": {"plan_split": doc["plan_split"]}})
    await db().paper_history.delete_many({"user_id": str(user["_id"])})
    await db().crypto_plans.update_one({"_id": body.plan_id}, {"$set": {"paper_started": True}})
    await events.track(db(), "paper_started", user_id=str(user["_id"]))
    return await view(user, doc)


@router.post("/paper/trade")
async def trade(body: TradeIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "paper_trade")
    sym = body.symbol.upper()
    if sym not in TRADABLE:
        raise HTTPException(status_code=400, detail={"code": "not_tradable", "msg": f"{sym} isn't in Paper Money. Try a top coin."})
    uid = str(user["_id"])
    doc = await db().paper.find_one({"_id": uid})
    if body.side == "buy":
        doc = await buy_many(user, {sym: body.amount_inr}, note="manual")
    else:
        if not doc or sym not in (doc.get("positions") or {}):
            raise HTTPException(status_code=400, detail={"code": "no_position", "msg": f"You don't hold {sym} in Paper Money."})
        px = (await _prices_inr([sym]))[sym]
        p = doc["positions"][sym]
        qty = min(p["qty"], body.amount_inr / px)
        frac = qty / p["qty"] if p["qty"] else 1
        p["cost_inr"] -= p["cost_inr"] * frac
        p["qty"] -= qty
        doc["cash_inr"] += qty * px
        if p["qty"] <= 1e-12:
            doc["positions"].pop(sym)
        doc["trades"] = (doc.get("trades") or [])[-199:] + [{"at": utcnow(), "symbol": sym, "side": "sell", "inr": qty * px,
                                                              "price_inr": px, "note": "manual"}]
        await db().paper.replace_one({"_id": uid}, doc)
    await events.track(db(), "paper_trade", user_id=uid, props={"symbol": sym, "side": body.side})
    return await view(user, doc)


@router.post("/paper/rebalance")
async def rebalance(user: dict = Depends(user_dep())):
    """Sell everything at live prices and buy the linked plan's current split with 90% of the total (10% stays as
    cash, like a fresh start). The value history and trade log are kept."""
    uid = str(user["_id"])
    doc = await db().paper.find_one({"_id": uid})
    if not doc or not doc.get("plan_id"):
        raise HTTPException(status_code=400, detail={"code": "no_paper", "msg": "Start Paper Money from a plan first."})
    plan = await db().crypto_plans.find_one({"_id": doc["plan_id"], "user_id": uid})
    if not plan:
        raise HTTPException(status_code=404, detail={"code": "no_plan", "msg": "The plan this practice money follows was deleted."})
    pos = doc.get("positions") or {}
    px = await _prices_inr(list(pos))
    missing = [s for s in pos if s not in px]
    if missing:
        raise HTTPException(status_code=503, detail={"code": "no_price", "msg": f"No price for {', '.join(missing)} right now. Try again shortly."})
    now = utcnow()
    trades = doc.get("trades") or []
    for s, p in pos.items():
        trades.append({"at": now, "symbol": s, "side": "sell", "inr": p["qty"] * px[s], "price_inr": px[s], "note": "rebalance"})
    total = doc["cash_inr"] + sum(p["qty"] * px[s] for s, p in pos.items())
    doc.update(cash_inr=total, positions={}, trades=trades[-200:])
    await db().paper.replace_one({"_id": uid}, doc)
    amounts = {a["symbol"]: total * 0.9 * a["pct"] / 100 for a in plan["allocation"]}
    doc = await buy_many(user, amounts, plan_id=plan["_id"], note="rebalance to plan")
    doc["plan_split"] = split_of(plan)
    await db().paper.update_one({"_id": uid}, {"$set": {"plan_split": doc["plan_split"]}})
    await events.track(db(), "paper_rebalanced", user_id=uid)
    return await view(user, doc)


@router.post("/paper/reset")
async def reset(user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    await db().paper.delete_one({"_id": uid})
    await db().paper_history.delete_many({"user_id": uid})
    await db().crypto_plans.update_many({"user_id": uid}, {"$set": {"paper_started": False}})
    return await view(user)


async def job_snapshot(ctx) -> dict:
    from pymongo import UpdateOne
    day = ctx.now.astimezone(IST).date().isoformat()
    n = 0
    px_cache: dict[str, float] = {}
    ops = []
    async for doc in ctx.db.paper.find({}, {"cash_inr": 1, "positions": 1}):
        pos = doc.get("positions") or {}
        missing = [s for s in pos if s not in px_cache]
        if missing:                                  # prices fetched once per coin, not once per member
            px_cache.update(await _prices_inr(missing))
        val = doc["cash_inr"] + sum(p["qty"] * px_cache.get(s, 0) for s, p in pos.items())
        ops.append(UpdateOne({"_id": f"{doc['_id']}:{day}"},
                             {"$set": {"user_id": doc["_id"], "date": day, "value_inr": val}}, upsert=True))
        n += 1
        if len(ops) >= 1000:
            await _bulk(ctx.db.paper_history, ops)
            ops = []
    if ops:
        await _bulk(ctx.db.paper_history, ops)
    return {"snapshots": n}


async def _bulk(coll, ops) -> None:
    try:
        await coll.bulk_write(ops, ordered=False)
    except TypeError:                                # mongomock (tests) can't take pymongo's UpdateOne: one by one
        for o in ops:
            await coll.update_one(o._filter, o._doc, upsert=o._upsert)
