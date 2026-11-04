"""SIP Autopilot plans and buys (from Bullzeye crypto/dca.py; INR amounts, coin or basket plans).

dca_plans {_id, user_id, kind coin|basket, venue, coin, basket_id, amount_inr, frequency weekly|monthly,
           weekday (0=Mon) | day (1–28), status active|paused, next_at, last_error, created_at}
dca_buys  {_id, plan_id, user_id, at, coin, inr, usdt, qty, price, order_id, venue}

Runs daily at 10:00 IST; a missed day buys on the next run (never twice). Before buying, the USDT
balance is checked: short → skip, note the error and alert the user to top up. Never sells.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from growth import events
from growth.clock import IST, as_utc

from . import tax, venue_name
from .exchanges import ExchangeError

MIN_INR_PER_COIN = 1000.0


def next_run(p: dict, after: datetime) -> datetime:
    local = as_utc(after).astimezone(IST)
    d = local.date() + timedelta(days=1)
    if p["frequency"] == "weekly":
        while d.weekday() != p.get("weekday", 0):
            d += timedelta(days=1)
    else:
        day = min(int(p.get("day", 1)), 28)
        while d.day != day:
            d += timedelta(days=1)
    return datetime.combine(d, time(10, 0), tzinfo=IST).astimezone(as_utc(after).tzinfo)


async def legs(db, p: dict) -> dict[str, float]:
    """INR per coin for one run of the plan."""
    if p.get("kind") == "basket":
        b = await db.baskets.find_one({"_id": p["basket_id"]})
        if not b or not b.get("active", True):
            raise ExchangeError("This basket is no longer available.", code="basket_gone")
        return {c["symbol"]: p["amount_inr"] * c["weight_pct"] / 100 for c in b["coins"]}
    return {p["coin"]: p["amount_inr"]}


async def execute(db, user_id: str, venue: str, amounts_inr: dict[str, float], *, ref: str, now: datetime,
                  note: str) -> list[dict]:
    """Market-buy each coin with USDT on the user's exchange. Checks the balance first (all or nothing)."""
    from . import links
    from .fx import usd_inr
    fx, _ = await usd_inr(db)
    ad = await links.adapter(db, user_id, venue)
    need_usdt = sum(amounts_inr.values()) / fx
    bal = await ad.balances()
    have = float(bal.get("USDT", 0.0))
    if have + 1e-6 < need_usdt:
        raise ExchangeError(f"Not enough USDT: this needs {need_usdt:,.2f} USDT and you have {have:,.2f} USDT. Top up on {venue_name(venue)}.",
                            code="short_usdt")
    out = []
    for i, (coin, inr) in enumerate(amounts_inr.items()):
        usdt = round(inr / fx, 2)
        try:
            o = await ad.market_buy_quote(f"{coin}USDT", usdt, f"cz{ref[-12:]}{i}{int(now.timestamp())}"[:36])
        except ExchangeError as e:
            out.append({"symbol": coin, "inr": round(inr, 2), "qty": 0.0, "price_usd": None, "status": f"failed: {e}"[:120]})
            continue
        px = o.avg_price or (usdt / o.filled_qty if o.filled_qty else 0)
        await db.dca_buys.insert_one({"_id": f"{ref}:{o.order_id}", "plan_id": ref, "user_id": user_id, "at": now,
                                      "coin": coin, "inr": round(inr, 2), "usdt": usdt, "qty": o.filled_qty, "price": px,
                                      "order_id": o.order_id, "venue": venue})
        await tax.record(db, user_id, "acquisition", coin, o.filled_qty, px, venue=venue, ref=f"buy:{o.order_id}",
                         ts=now, note=note)
        await events.track(db, "dca_bought", user_id=user_id, props={"coin": coin, "inr": round(inr)})
        out.append({"symbol": coin, "inr": round(inr, 2), "qty": o.filled_qty, "price_usd": px, "status": "filled"})
    return out


async def run_job(ctx) -> dict:
    from core.flags import is_on
    from notify.service import alert
    from . import links
    if not is_on("AUTOPILOT"):
        return {"status": "off"}
    import asyncio
    import os
    db, now = ctx.db, ctx.now
    tally = {"bought": 0, "failed": 0}
    # Each member's buy runs on their own exchange key, so several can run at once (exchange rate limits are
    # per key). Sequential, 10,000 plans × ~0.3 s exchange round trip would take ~50 minutes.
    sem = asyncio.Semaphore(int(os.environ.get("AUTOPILOT_CONCURRENCY", "10") or 10))

    async def one(p: dict) -> None:
        async with sem:
            nxt = next_run(p, now)
            claim = await db.dca_plans.update_one({"_id": p["_id"], "next_at": p["next_at"]}, {"$set": {"next_at": nxt}})
            if claim.modified_count != 1:
                return
            name = p.get("coin") or p.get("basket_name") or "basket"
            try:
                amounts = await legs(db, p)
                rows = await execute(db, p["user_id"], p["venue"], amounts, ref=p["_id"], now=now, note="Autopilot buy")
            except (ExchangeError, links.LinkError) as e:
                msg = str(e)
                await db.dca_plans.update_one({"_id": p["_id"]}, {"$set": {"last_error": msg[:160], "last_error_at": now}})
                await events.track(db, "dca_failed", user_id=p["user_id"], props={"reason": getattr(e, "code", "error")})
                await alert(db, p["user_id"], "autopilot", f"Autopilot couldn't buy {name}", msg[:300], link="/app/autopilot",
                            dedupe=f"apf:{p['_id']}:{now.date().isoformat()}")
                tally["failed"] += 1
                return
            ok = [r for r in rows if r["status"] == "filled"]
            await db.dca_plans.update_one({"_id": p["_id"]}, {"$set": {"last_error": None if ok else rows[0]["status"]}})
            if ok:
                await alert(db, p["user_id"], "autopilot", f"Autopilot bought {name}",
                            ", ".join(f"₹{r['inr']:,.0f} of {r['symbol']}" for r in ok) + f" on {venue_name(p['venue'])}.",
                            link="/app/autopilot", dedupe=f"apb:{p['_id']}:{now.date().isoformat()}")
                tally["bought"] += 1

    due = [p async for p in db.dca_plans.find({"status": "active", "next_at": {"$lte": now}})]
    for k in range(0, len(due), 500):
        await asyncio.gather(*(one(p) for p in due[k:k + 500]))
    return tally


async def summary(db, user_id: str, prices_usd: dict[str, float], fx: float) -> list[dict]:
    out = []
    async for p in db.dca_plans.find({"user_id": user_id}).sort("created_at", 1):
        invested = 0.0
        value = 0.0
        n = 0
        recent = []
        async for b in db.dca_buys.find({"plan_id": p["_id"]}).sort("at", -1):
            invested += b.get("inr") or 0
            value += b["qty"] * prices_usd.get(b["coin"], 0) * fx
            n += 1
            if len(recent) < 6:
                recent.append({"at": as_utc(b["at"]).isoformat(), "coin": b["coin"], "qty": b["qty"],
                               "price_usd": b["price"], "inr": b.get("inr")})
        out.append({"id": p["_id"], "kind": p.get("kind", "coin"), "venue": p["venue"], "coin": p.get("coin"),
                    "basket_id": p.get("basket_id"), "basket_name": p.get("basket_name"),
                    "amount_inr": p["amount_inr"], "frequency": p["frequency"], "weekday": p.get("weekday"),
                    "day": p.get("day"), "status": p["status"],
                    "next_at": as_utc(p["next_at"]).isoformat() if p.get("next_at") else None,
                    "last_error": p.get("last_error"), "buys": n, "invested_inr": round(invested, 2),
                    "value_inr": round(value, 2),
                    "return_pct": round((value / invested - 1) * 100, 2) if invested else None, "recent": recent})
    return out
