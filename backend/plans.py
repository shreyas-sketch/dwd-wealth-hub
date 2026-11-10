"""Plans, feature access and monthly limits.

free / lite (₹2,000 a month) / pro (₹5,000 a month).

Effective plan = the highest of: an active paid subscription, an admin grant, the trial
(new accounts get `pro` until users.trial_ends_at), admin role (pro). Limits reset on the
1st of each IST month:

    usage {_id: "<uid>:<YYYY-MM>", user_id, month, <feature>: n}

`require()` raises 403 {code: locked}; `consume()` raises 402 {code: limit}.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from growth import events
from growth.clock import as_utc, ist_month_key, utcnow

PLANS = ("free", "lite", "pro")
RANK = {"free": 0, "lite": 1, "pro": 2}
LABELS = {"free": "Free", "lite": "₹2,000 plan", "pro": "₹5,000 plan"}
PRICES_INR = {"lite": 2000, "pro": 5000}          # list price, before GST (also what MRR counts)
GST_PCT = 18


def total_inr(plan: str) -> int:
    """What the member is charged each month: list price + 18% GST (₹2,360 / ₹5,900)."""
    return round(PRICES_INR.get(plan, 0) * (100 + GST_PCT) / 100)

# Lowest plan that opens each feature.
FEATURE_MIN: dict[str, str] = {
    "whatif": "free", "xray": "free", "verdicts": "free", "plan": "free",
    "verdict_details": "lite", "forecast": "lite", "debate": "lite", "pulse": "lite", "watchlist": "lite",
    "monday_picks": "lite", "paper_trade": "lite", "airdrops": "lite", "autopilot": "lite", "chart": "lite",
    "ask": "pro", "baskets": "pro", "radar": "pro", "calendar": "pro", "p2p": "pro", "news": "pro",
}
FEATURE_NAMES = {
    "whatif": "What If", "xray": "Coin X-Ray", "verdicts": "Crypto Verdicts", "verdict_details": "Verdict details",
    "forecast": "Forecast", "debate": "Bull vs Bear debate", "pulse": "Market Pulse", "watchlist": "Watchlist alerts",
    "monday_picks": "Monday Crypto Picks", "plan": "My Crypto Plan", "paper_trade": "Paper Money trades",
    "airdrops": "Airdrop Finder", "autopilot": "SIP Autopilot", "chart": "Chart Reader", "ask": "Ask Deepak AI",
    "baskets": "Crypto Baskets", "radar": "Early Coin Radar", "calendar": "Crypto Events Calendar",
    "p2p": "P2P Rate Finder", "news": "News Decoder",
}

# Monthly limits (None = unlimited). Metered features only.
LIMITS: dict[str, dict[str, Optional[int]]] = {
    "xray": {"free": 3, "lite": 30, "pro": None},
    "forecast": {"free": 0, "lite": 10, "pro": None},
    "debate": {"free": 0, "lite": 10, "pro": None},
    "chart": {"free": 0, "lite": 10, "pro": None},
    "ask": {"free": 0, "lite": 0, "pro": None},
}
LIMIT_UNITS = {"xray": "Coin X-Ray checks", "forecast": "Forecasts", "debate": "Bull vs Bear debates",
               "chart": "Chart Reader reads", "ask": "Ask Deepak questions"}
FAIR_USE = {"ask": 300, "xray": 1000, "forecast": 300, "debate": 300, "chart": 300}

AUTOPILOT = {
    "free": {"coins": [], "frequencies": []},
    "lite": {"coins": ["BTC"], "frequencies": ["monthly"]},
    "pro": {"coins": ["BTC", "ETH", "SOL", "XRP"], "frequencies": ["weekly", "monthly"]},
}
PLANS_MAX = {"free": 1, "lite": 1, "pro": 3}

CATALOG = [
    {"id": "free", "name": "Free", "price_inr": 0, "gst_pct": 0, "gst_inr": 0, "total_inr": 0, "period": "month", "features": [
        "What If calculator", "Coin X-Ray: 3 checks a month", "Today's AI verdicts on the top 10 coins",
        "Make your crypto plan (view)", "Paper Money (view)"]},
    {"id": "lite", "name": "₹2,000 plan", "price_inr": 2000, "gst_pct": 18, "gst_inr": 360, "total_inr": 2360, "period": "month", "features": [
        "Coin X-Ray with Scam Check: 30 checks a month",
        "Crypto Verdicts: Market Pulse, Bitcoin Cycle Meter, watchlist alerts, Monday Picks; 10 Forecasts + 10 Debates a month",
        "My Crypto Plan + ₹1 lakh Paper Money, with your KuCoin/Binance holdings",
        "Airdrop Finder", "SIP Autopilot: BTC, monthly", "Chart Reader: 10 charts a month"]},
    {"id": "pro", "name": "₹5,000 plan", "price_inr": 5000, "gst_pct": 18, "gst_inr": 900, "total_inr": 5900, "period": "month", "features": [
        "Everything in ₹2,000, without limits", "Up to 3 crypto plans",
        "SIP Autopilot: BTC, ETH, SOL, XRP — weekly or monthly", "Ask Deepak AI", "Crypto Baskets",
        "Early Coin Radar", "Crypto Events Calendar", "P2P Rate Finder", "News Decoder"]},
]


def plan_allows(plan: str, feature: str) -> bool:
    return RANK[plan] >= RANK[FEATURE_MIN.get(feature, "pro")]


def _uid(user) -> str:
    return str(user["_id"]) if isinstance(user, dict) else str(user)


async def effective_plan(db, user: dict, now: Optional[datetime] = None) -> dict:
    """{plan, source, trial_ends_at, paid_until, cancelling}"""
    now = now or utcnow()
    uid = _uid(user)
    cands: list[tuple[str, str, Optional[datetime]]] = []   # (plan, source, until)
    if (user.get("role") or "user") == "admin":
        cands.append(("pro", "grant", None))
    renewing = False
    async for s in db.subscriptions.find({"user_id": uid, "status": {"$in": ["active", "authenticated", "pending"]}}):
        end = s.get("current_end")
        if end and as_utc(end) > now and s.get("plan") in PLANS:
            cands.append((s["plan"], "paid", as_utc(end)))
            renewing = renewing or not s.get("cancel_at_cycle_end")
    async for g in db.plan_grants.find({"user_id": uid}):
        if g.get("ends_at") and as_utc(g["ends_at"]) > now and g.get("plan") in PLANS:
            cands.append((g["plan"], "grant", as_utc(g["ends_at"])))
    trial_end = user.get("trial_ends_at")
    if trial_end and as_utc(trial_end) > now:
        cands.append(("pro", "trial", as_utc(trial_end)))
    order = {"paid": 3, "grant": 2, "trial": 1}
    best = ("free", "free", None)
    for c in cands:
        if RANK[c[0]] > RANK[best[0]] or (RANK[c[0]] == RANK[best[0]] and order.get(c[1], 0) > order.get(best[1], 0)):
            best = c
    paid = [c for c in cands if c[1] == "paid"]
    return {"plan": best[0], "source": best[1],
            "trial_ends_at": as_utc(trial_end).isoformat() if trial_end else None,
            "paid_until": max(c[2] for c in paid).isoformat() if paid else None,
            "cancelling": bool(paid) and not renewing}     # cancelled: runs to paid_until, won't renew


async def nonfree_plans(db, now: Optional[datetime] = None) -> dict[str, str]:
    """user_id → effective plan for everyone NOT on free, in three queries (instead of two per user).
    Same precedence as effective_plan: best of live subscription, admin grant, trial (= pro), admin role (= pro).
    Used by admin filters and by jobs that alert thousands of members."""
    now = now or utcnow()
    best: dict[str, str] = {}

    def up(uid: str, p: Optional[str]) -> None:
        if p in PLANS and RANK[p] > RANK[best.get(uid, "free")]:
            best[uid] = p
    async for s in db.subscriptions.find({"status": {"$in": ["active", "authenticated", "pending"]},
                                         "current_end": {"$gt": now}}, {"user_id": 1, "plan": 1}):
        up(s["user_id"], s.get("plan"))
    async for g in db.plan_grants.find({"ends_at": {"$gt": now}}, {"user_id": 1, "plan": 1}):
        up(g["user_id"], g.get("plan"))
    async for u in db.users.find({"$or": [{"trial_ends_at": {"$gt": now}}, {"role": "admin"}]}, {"_id": 1}):
        up(str(u["_id"]), "pro")
    return best


async def users_with(db, feature: str, now: Optional[datetime] = None) -> list[str]:
    """Ids of active (not revoked) members whose plan includes `feature`, resolved in bulk for job fan-outs."""
    now = now or utcnow()
    need = FEATURE_MIN.get(feature, "pro")
    if need == "free":
        return [str(u["_id"]) async for u in db.users.find({"status": {"$ne": "revoked"}}, {"_id": 1})]
    revoked = {str(u["_id"]) async for u in db.users.find({"status": "revoked"}, {"_id": 1})}
    return [uid for uid, p in (await nonfree_plans(db, now)).items() if RANK[p] >= RANK[need] and uid not in revoked]


async def usage_doc(db, uid: str, now: Optional[datetime] = None) -> dict:
    return await db.usage.find_one({"_id": f"{uid}:{ist_month_key(now)}"}) or {}


async def plan_info(db, user: dict) -> dict:
    ep = await effective_plan(db, user)
    plan = ep["plan"]
    u = await usage_doc(db, _uid(user))
    return {**ep, "label": LABELS[plan],
            "features": {f: plan_allows(plan, f) for f in FEATURE_MIN},
            "limits": {f: {"used": int(u.get(f, 0)), "limit": lim[plan]} for f, lim in LIMITS.items()},
            "autopilot": AUTOPILOT[plan], "plans_max": PLANS_MAX[plan]}


def needed_for(feature: str) -> str:
    need = FEATURE_MIN.get(feature, "pro")
    return "lite" if need == "free" else need


def locked_error(feature: str, plan_needed: Optional[str] = None) -> HTTPException:
    need = plan_needed or needed_for(feature)
    return HTTPException(status_code=403, detail={
        "code": "locked", "feature": feature, "plan_needed": need,
        "msg": f"{FEATURE_NAMES.get(feature, feature)} is part of the {LABELS[need]}."})


async def require(db, user: dict, feature: str) -> str:
    """Returns the plan; raises 403 locked if the plan doesn't include the feature."""
    plan = (await effective_plan(db, user))["plan"]
    if not plan_allows(plan, feature):
        await events.track(db, "locked_hit", user_id=_uid(user), props={"feature": feature, "plan": plan})
        raise locked_error(feature)
    return plan


async def consume(db, user: dict, feature: str, plan: Optional[str] = None) -> dict:
    """Meter one use. Returns usage {used, limit}. Raises 402 limit (or 403 locked when the limit is 0)."""
    uid = _uid(user)
    plan = plan or (await effective_plan(db, user))["plan"]
    limit = LIMITS[feature][plan]
    key = f"{uid}:{ist_month_key()}"
    doc = await db.usage.find_one({"_id": key}) or {}
    used = int(doc.get(feature, 0))
    if limit == 0:
        await events.track(db, "locked_hit", user_id=uid, props={"feature": feature, "plan": plan})
        raise locked_error(feature, "pro" if LIMITS[feature]["lite"] == 0 else "lite")
    cap = limit if limit is not None else FAIR_USE.get(feature)
    if cap is not None and used >= cap:
        await events.track(db, "limit_hit", user_id=uid, props={"feature": feature, "plan": plan})
        nxt = "pro" if plan == "lite" else "lite" if plan == "free" else None
        raise HTTPException(status_code=402, detail={
            "code": "limit", "feature": feature, "used": used, "limit": cap, "plan_needed": nxt,
            "msg": (f"You've used all {cap} {LIMIT_UNITS.get(feature, FEATURE_NAMES[feature] + ' uses')} this month."
                    + (f" The {LABELS[nxt]} gives you more." if nxt else " It resets on the 1st."))})
    await db.usage.update_one({"_id": key}, {"$inc": {feature: 1},
                                             "$setOnInsert": {"user_id": uid, "month": ist_month_key()}}, upsert=True)
    return {"used": used + 1, "limit": limit}


async def refund(db, user: dict, feature: str) -> None:
    await db.usage.update_one({"_id": f"{_uid(user)}:{ist_month_key()}", feature: {"$gt": 0}}, {"$inc": {feature: -1}})


async def anon_consume(db, anon_key: str, feature: str, per_day: int) -> dict:
    from growth.clock import IST
    day = utcnow().astimezone(IST).date().isoformat()
    key = f"{anon_key}:{feature}:{day}"
    doc = await db.anon_usage.find_one({"_id": key}) or {}
    used = int(doc.get("n", 0))
    if used >= per_day:
        # 402 "limit" (contract); `signup: true` tells the public page to offer the free account.
        raise HTTPException(status_code=402, detail={
            "code": "limit", "signup": True, "plan_needed": "free", "feature": feature, "used": used, "limit": per_day,
            "msg": "Create an account to keep checking. It is free and takes 30 seconds."})
    await db.anon_usage.update_one({"_id": key}, {"$inc": {"n": 1}, "$setOnInsert": {"at": utcnow()}}, upsert=True)
    return {"used": used + 1, "limit": per_day}
