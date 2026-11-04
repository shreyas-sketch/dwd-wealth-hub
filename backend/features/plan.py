"""My Crypto Plan (+ the real portfolio from linked exchanges).

crypto_plans {_id, user_id, goal_name, target_inr, lump_sum_inr, monthly_inr, years, risk, allocation,
              paper_started, created_at, updated_at}

Scenarios compound monthly at the admin's assumed yearly rates (Admin › Settings, default bad 0%,
average 15%, good 35%) — always shown as assumptions, never as a promise.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import appsettings
import market
import plans
from core.deps import user_dep
from crypto.fx import usd_inr
from growth import events
from growth.clock import utcnow
from state import db
from util import iso, smart_round

router = APIRouter(tags=["plan"])

ALLOCATIONS = {
    "safe": [("BTC", 70), ("ETH", 20), ("USDT", 10)],
    "moderate": [("BTC", 50), ("ETH", 30), ("SOL", 10), ("XRP", 10)],
    "aggressive": [("BTC", 40), ("ETH", 25), ("SOL", 20), ("XRP", 15)],
}
LABELS = {"bad": "Bad market", "average": "Average market", "good": "Good market"}
NOTE = ("These are assumed yearly growth rates to help you plan, not a promise. Crypto can also fall a lot and stay "
        "down for years. USDT is a dollar-linked stable coin kept as a cushion.")


class PlanIn(BaseModel):
    goal_name: str = Field(..., min_length=1, max_length=60)
    target_inr: float = Field(..., ge=10_000, le=1_000_000_000)
    lump_sum_inr: float = Field(0, ge=0, le=100_000_000)
    monthly_inr: float = Field(0, ge=0, le=1_000_000)
    years: int = Field(..., ge=1, le=30)
    risk: Literal["safe", "moderate", "aggressive"] = "moderate"


def project(lump: float, monthly: float, years: int, annual_pct: float) -> list[float]:
    """Value at the end of each year."""
    r = (1 + annual_pct / 100) ** (1 / 12) - 1
    v, out = lump, []
    for m in range(1, years * 12 + 1):
        v = (v + monthly) * (1 + r)
        if m % 12 == 0:
            out.append(v)
    return out


async def portfolio_for(user: dict) -> dict:
    uid = str(user["_id"])
    from crypto import links
    holdings, linked = [], []
    async for l in db().exchange_links.find({"user_id": uid, "status": "active"}):
        try:
            ad = await links.adapter(db(), uid, l["venue"])
            bal = await ad.balances()
        except Exception:  # noqa: BLE001 — a venue hiccup shouldn't break the screen
            continue
        linked.append(l["venue"])
        for asset, qty in bal.items():
            if qty and qty > 0:
                holdings.append({"venue": l["venue"], "symbol": asset.upper(), "qty": qty})
    fx, _ = await usd_inr(db())
    px = await market.prices([h["symbol"] for h in holdings]) if holdings else {}
    total_usd = 0.0
    for h in holdings:
        p = (px.get(h["symbol"]) or {}).get("price_usd") or (1.0 if h["symbol"] in market.STABLES else 0.0)
        h["price_usd"] = smart_round(p)
        h["value_usd"] = round(h["qty"] * p, 2)
        h["value_inr"] = round(h["qty"] * p * fx, 2)
        total_usd += h["value_usd"]
    holdings = [h for h in holdings if h["value_usd"] >= 0.5]
    holdings.sort(key=lambda h: -h["value_usd"])
    vs = []
    first = await db().crypto_plans.find_one({"user_id": uid}, sort=[("created_at", 1)])
    if first and total_usd > 0:
        by = {}
        for h in holdings:
            sym = "USDT" if h["symbol"] in market.STABLES else h["symbol"]
            by[sym] = by.get(sym, 0) + h["value_usd"]
        for a in first["allocation"]:
            vs.append({"symbol": a["symbol"], "plan_pct": a["pct"], "actual_pct": round(by.get(a["symbol"], 0) / total_usd * 100, 1)})
    return {"linked": sorted(set(linked)), "holdings": holdings, "total_usd": round(total_usd, 2),
            "total_inr": round(total_usd * fx, 2), "vs_plan": vs, "as_of": iso(utcnow())}


async def shape(user: dict, p: dict, rates: dict, portfolio: Optional[dict] = None, paper: Optional[dict] = None) -> dict:
    years = p["years"]
    proj = {k: project(p["lump_sum_inr"], p["monthly_inr"], years, rates[k]) for k in ("bad", "average", "good")}
    yearly = [{"year": y + 1, "invested_inr": round(p["lump_sum_inr"] + p["monthly_inr"] * 12 * (y + 1)),
               "bad_inr": round(proj["bad"][y]), "average_inr": round(proj["average"][y]), "good_inr": round(proj["good"][y])}
              for y in range(years)]
    scen = [{"key": k, "label": LABELS[k], "annual_pct": rates[k], "end_value_inr": round(proj[k][-1]),
             "reaches_goal": proj[k][-1] >= p["target_inr"]} for k in ("bad", "average", "good")]
    value, source = 0.0, "none"
    if portfolio and portfolio.get("total_inr"):
        value, source = portfolio["total_inr"], "portfolio"
    elif paper and paper.get("plan_id") == p["_id"] and paper.get("started_at"):
        value, source = paper["value_inr"], "paper"
    return {"id": p["_id"], "goal_name": p["goal_name"], "target_inr": p["target_inr"], "lump_sum_inr": p["lump_sum_inr"],
            "monthly_inr": p["monthly_inr"], "years": years, "risk": p["risk"],
            "allocation": [{"symbol": s, "pct": pct} for s, pct in ((a["symbol"], a["pct"]) for a in p["allocation"])],
            "invested_total_inr": round(p["lump_sum_inr"] + p["monthly_inr"] * 12 * years), "scenarios": scen,
            "yearly": yearly,
            "goal_progress": {"value_inr": round(value, 2), "pct": round(min(100.0, value / p["target_inr"] * 100), 1) if value else 0.0,
                              "source": source},
            "paper_started": bool(p.get("paper_started")), "created_at": iso(p.get("created_at")), "note": NOTE}


async def _context(user: dict) -> tuple[dict, Optional[dict], Optional[dict]]:
    rates = (await appsettings.get(db()))["scenario_rates"]
    portfolio = None
    if await db().exchange_links.count_documents({"user_id": str(user["_id"]), "status": "active"}):
        portfolio = await portfolio_for(user)
    from features.paper import view
    paper = await view(user)
    return rates, portfolio, paper


@router.get("/plan")
async def list_plans(user: dict = Depends(user_dep())):
    info = await plans.effective_plan(db(), user)
    rates, portfolio, paper = await _context(user)
    rows = [p async for p in db().crypto_plans.find({"user_id": str(user["_id"])}).sort("created_at", 1)]
    return {"plans": [await shape(user, p, rates, portfolio, paper) for p in rows], "max": plans.PLANS_MAX[info["plan"]]}


def _doc(body: PlanIn) -> dict:
    return {"goal_name": body.goal_name.strip(), "target_inr": body.target_inr, "lump_sum_inr": body.lump_sum_inr,
            "monthly_inr": body.monthly_inr, "years": body.years, "risk": body.risk,
            "allocation": [{"symbol": s, "pct": pct} for s, pct in ALLOCATIONS[body.risk]]}


@router.post("/plan")
async def create(body: PlanIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    info = await plans.effective_plan(db(), user)
    mx = plans.PLANS_MAX[info["plan"]]
    if await db().crypto_plans.count_documents({"user_id": uid}) >= mx:
        if info["plan"] == "pro":       # already on the top plan: nothing to upgrade to
            raise HTTPException(status_code=400, detail={
                "code": "plans_full", "msg": f"You can keep up to {mx} crypto plans. Delete one to make a new one."})
        raise HTTPException(status_code=403, detail={
            "code": "locked", "feature": "plan", "plan_needed": "pro",
            "msg": f"Your plan holds {mx} crypto plan{'s' if mx > 1 else ''}. The ₹5,000 plan holds 3."})
    if body.lump_sum_inr <= 0 and body.monthly_inr <= 0:
        raise HTTPException(status_code=400, detail={"code": "no_amount", "msg": "Add a one-time amount or a monthly amount."})
    now = utcnow()
    p = {"_id": uuid.uuid4().hex[:16], "user_id": uid, **_doc(body), "paper_started": False, "created_at": now, "updated_at": now}
    await db().crypto_plans.insert_one(p)
    await events.track(db(), "plan_saved", user_id=uid, props={"risk": body.risk})
    rates, portfolio, paper = await _context(user)
    return await shape(user, p, rates, portfolio, paper)


@router.put("/plan/{plan_id}")
async def update(plan_id: str, body: PlanIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    p = await db().crypto_plans.find_one({"_id": plan_id, "user_id": uid})
    if not p:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Plan not found."})
    p.update(_doc(body), updated_at=utcnow())
    await db().crypto_plans.replace_one({"_id": plan_id}, p)
    await events.track(db(), "plan_saved", user_id=uid, props={"risk": body.risk})
    rates, portfolio, paper = await _context(user)
    return await shape(user, p, rates, portfolio, paper)


@router.delete("/plan/{plan_id}")
async def delete(plan_id: str, user: dict = Depends(user_dep())):
    await db().crypto_plans.delete_one({"_id": plan_id, "user_id": str(user["_id"])})
    return {"ok": True}


@router.get("/portfolio")
async def portfolio(user: dict = Depends(user_dep())):
    return await portfolio_for(user)
