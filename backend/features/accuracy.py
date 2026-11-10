"""Verdict hit rate: were the daily Bullish / Neutral / Bearish calls right, and did they beat chance?

Scoring (job `verdict_scoring`, daily 05:45 IST, right after the 05:30 verdicts):
  For each verdict and each horizon (7 and 30 days) the job records one outcome:
    start  the price stored with the verdict (taken when it was made)
    end    the live price now, for verdicts made exactly 7 / 30 days ago (same time of day as the start), or
           the daily close of the target date for ones the job missed (end_basis "daily_close")
    right  Bullish: up more than the band · Bearish: down more than the band · Neutral: within ±band
           (band = 3% over 7 days, 6% over 30 days; small moves are noise, not a call coming true)

Reading the numbers (GET /api/admin/verdicts/accuracy):
  hit rate        share of calls that were right, with a 95% range (Wilson interval); under 30 calls it is noise
  chance          the hit rate you'd get by always giving that verdict: e.g. if coins rose >3% in 40% of all
                  scored weeks, "Bullish right 45%" is only 5 points of skill
  spread          average return after Bullish minus after Bearish: positive means the calls point the right way
  by confidence   whether 70%+ calls are right more often than 50–59% ones (they should be)

verdict_outcomes {_id: "<date>:<symbol>:<h>", date, symbol, verdict, confidence, horizon, price_start, price_end,
                  return_pct, correct, end_basis: "live" | "daily_close", scored_at}
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

import market
from growth.clock import IST, utcnow

HORIZONS = (7, 30)
BAND_PCT = {7: 3.0, 30: 6.0}
LOOKBACK_DAYS = 120            # how far back the job fills gaps it missed
MIN_CALLS = 30                 # below this, a hit rate is mostly luck
VERDICTS = ("Bullish", "Neutral", "Bearish")


def judge(verdict: str, return_pct: float, horizon: int) -> Optional[bool]:
    band = BAND_PCT[horizon]
    if verdict == "Bullish":
        return return_pct > band
    if verdict == "Bearish":
        return return_pct < -band
    if verdict == "Neutral":
        return abs(return_pct) <= band
    return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[Optional[float], Optional[float]]:
    """95% range for a hit rate of k out of n (stays sensible for small n, unlike ±2 standard errors)."""
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(max(0.0, mid - half) * 100, 1), round(min(1.0, mid + half) * 100, 1)


def _start_price(v: dict) -> Optional[float]:
    p = v.get("price_usd") or (v.get("indicators") or {}).get("price")
    try:
        return float(p) if p and float(p) > 0 else None
    except (TypeError, ValueError):
        return None


def _outcome(v: dict, h: int, end: float, basis: str, now) -> Optional[dict]:
    start = _start_price(v)
    if not start or not end or v.get("verdict") not in VERDICTS:
        return None
    ret = round((end / start - 1) * 100, 2)
    return {"_id": f"{v['date']}:{v['symbol']}:{h}", "date": v["date"], "symbol": v["symbol"], "verdict": v["verdict"],
            "confidence": int(v.get("confidence") or 50), "horizon": h, "price_start": start, "price_end": end,
            "return_pct": ret, "correct": judge(v["verdict"], ret, h), "end_basis": basis, "scored_at": now}


async def job_score(ctx) -> dict:
    d, now = ctx.db, ctx.now
    today = now.astimezone(IST).date()
    scored = {h: 0 for h in HORIZONS}
    skipped = 0
    for h in HORIZONS:
        newest = (today - timedelta(days=h)).isoformat()
        oldest = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
        done = {o["_id"] async for o in d.verdict_outcomes.find({"horizon": h, "date": {"$gte": oldest, "$lte": newest}},
                                                                 {"_id": 1})}
        todo = [v async for v in d.verdicts.find({"date": {"$gte": oldest, "$lte": newest}})
                if f"{v['date']}:{v['symbol']}:{h}" not in done]
        if not todo:
            continue
        exact = [v for v in todo if v["date"] == newest]
        live = await market.prices(sorted({v["symbol"] for v in exact})) if exact else {}
        closes: dict[str, dict[str, float]] = {}
        for v in todo:
            if v["date"] == newest and (live.get(v["symbol"]) or {}).get("price_usd"):
                end, basis = live[v["symbol"]]["price_usd"], "live"
            else:
                sym = v["symbol"]
                if sym not in closes:
                    try:
                        closes[sym] = dict(await market.history(sym, LOOKBACK_DAYS + 5))
                    except Exception:  # noqa: BLE001 — try again tomorrow
                        closes[sym] = {}
                target = (date.fromisoformat(v["date"]) + timedelta(days=h)).isoformat()
                end, basis = closes[sym].get(target), "daily_close"
            row = _outcome(v, h, end, basis, now)
            if not row:
                skipped += 1
                continue
            await d.verdict_outcomes.update_one({"_id": row["_id"]}, {"$setOnInsert": row}, upsert=True)
            scored[h] += 1
    return {"scored_7d": scored[7], "scored_30d": scored[30], "skipped": skipped}


# ---------------------------------------------------------------- report ----
def _rate(rows: list[dict]) -> dict:
    n = len(rows)
    k = sum(1 for r in rows if r["correct"])
    lo, hi = wilson(k, n)
    return {"calls": n, "right": k, "hit_rate_pct": round(k / n * 100, 1) if n else None, "range_pct": [lo, hi],
            "avg_return_pct": round(sum(r["return_pct"] for r in rows) / n, 2) if n else None}


def _bucket(conf: int) -> str:
    return "70% and up" if conf >= 70 else "60–69%" if conf >= 60 else "50–59%"


def horizon_report(rows: list[dict], h: int) -> dict:
    out = {"horizon_days": h, "band_pct": BAND_PCT[h], **_rate(rows), "enough_data": len(rows) >= MIN_CALLS}
    by_verdict = []
    for v in VERDICTS:
        sub = [r for r in rows if r["verdict"] == v]
        # chance: how often this verdict would have been right if it were given for every coin-day scored
        chance_k = sum(1 for r in rows if judge(v, r["return_pct"], h))
        rate = _rate(sub)
        chance = round(chance_k / len(rows) * 100, 1) if rows else None
        by_verdict.append({"verdict": v, **rate, "chance_pct": chance,
                           "edge_pts": round(rate["hit_rate_pct"] - chance, 1) if sub and chance is not None else None})
    out["by_verdict"] = by_verdict
    bull = next(x for x in by_verdict if x["verdict"] == "Bullish")["avg_return_pct"]
    bear = next(x for x in by_verdict if x["verdict"] == "Bearish")["avg_return_pct"]
    out["spread_pct"] = round(bull - bear, 2) if bull is not None and bear is not None else None
    out["by_confidence"] = [{"bucket": b, **_rate([r for r in rows if _bucket(r["confidence"]) == b])}
                            for b in ("50–59%", "60–69%", "70% and up")]
    coins = sorted({r["symbol"] for r in rows})
    out["by_coin"] = sorted(({"symbol": s, **_rate([r for r in rows if r["symbol"] == s])} for s in coins),
                            key=lambda x: (-(x["calls"]), x["symbol"]))
    return out


async def summary(d, days: int = 90) -> dict:
    today = utcnow().astimezone(IST).date()
    since = (today - timedelta(days=days)).isoformat()
    rows = [o async for o in d.verdict_outcomes.find({"date": {"$gte": since}}, {"_id": 0})]
    recent = sorted((r for r in rows if r["horizon"] == 7), key=lambda r: (r["date"], r["symbol"]), reverse=True)[:20]
    return {"days": days, "since": since, "min_calls": MIN_CALLS,
            "horizons": [horizon_report([r for r in rows if r["horizon"] == h], h) for h in HORIZONS],
            "recent": [{k: r[k] for k in ("date", "symbol", "verdict", "confidence", "return_pct", "correct", "end_basis")}
                       for r in recent]}


# ---------------------------------------------------------------- QA seed ----
async def seed_backtest(d, days: int = 60) -> int:
    """QA only: past verdicts from the rules, using only the history each day could have seen, so the accuracy
    screen has something to show. Marked `backtest: true`. Never runs outside QA mode (see seed.py)."""
    from features.verdicts import indicators, rule_verdict
    today = utcnow().astimezone(IST).date()
    n = 0
    for c in await market.top_coins(10):
        sym = c["symbol"]
        hist = await market.history(sym, days + 200)
        for i in range(len(hist)):
            day = hist[i][0]
            if day >= today.isoformat() or day < (today - timedelta(days=days)).isoformat():
                continue
            closes = [p for _, p in hist[: i + 1]]
            if len(closes) < 60:
                continue
            ind = indicators(closes)
            v, conf, _, _ = rule_verdict(ind, c.get("rank"))
            res = await d.verdicts.update_one({"_id": f"{day}:{sym}"}, {"$setOnInsert": {
                "date": day, "symbol": sym, "name": c.get("name"), "rank": c.get("rank"), "verdict": v, "confidence": conf,
                "price_usd": closes[-1], "backtest": True, "created_at": utcnow(), "bull": [], "bear": [],
                "summary": None, "chair": None, "changed_from": None}}, upsert=True)
            n += 1 if res.upserted_id else 0
    return n
