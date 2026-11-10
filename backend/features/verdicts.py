"""Crypto Verdicts: daily AI committee on the top 10 coins, Forecast, Debate, Market Pulse with the
Bitcoin Cycle Meter, watchlist alerts and Monday Picks.

verdicts {_id: "<date>:<SYM>", date, symbol, name, verdict, confidence, summary, bull, bear, chair,
          price_usd, indicators, changed_from, created_at}
watchlists {_id: uid, symbols}
picks {_id: week_of (YYYY-MM-DD Monday), published, picks: [{symbol, name, verdict, confidence, reasoning, price_at_pick_usd}]}
etf_flows {_id: date, date, net_usd_m, note}
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import llm
import market
import plans
from auth import optional_user
from core.deps import user_dep
from core.flags import is_on
from core.vendors import vendor_mode
from crypto.fx import usd_inr
from features import DISCLAIMER
from growth import events
from growth.clock import IST, utcnow
from notify.service import alert
from state import db
from util import iso, r2, smart_round

router = APIRouter(tags=["verdicts"])

HALVINGS = [date(2012, 11, 28), date(2016, 7, 9), date(2020, 5, 11), date(2024, 4, 20)]
NEXT_HALVING_EST = date(2028, 4, 15)


def today_ist() -> str:
    return utcnow().astimezone(IST).date().isoformat()


# ------------------------------------------------------------------ indicators ----
def ema(vals: list[float], n: int) -> float:
    k = 2 / (n + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def rsi(vals: list[float], n: int = 14) -> float:
    gains, losses = [], []
    for a, b in zip(vals[-n - 1:-1], vals[-n:]):
        d = b - a
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    g, l = sum(gains) / n, sum(losses) / n
    return 100.0 if l == 0 else round(100 - 100 / (1 + g / l), 1)


def indicators(closes: list[float]) -> dict:
    last = closes[-1]
    rets = [math.log(b / a) for a, b in zip(closes[:-1], closes[1:]) if a > 0 and b > 0]
    vol = statistics.pstdev(rets[-30:]) if len(rets) >= 30 else (statistics.pstdev(rets) if len(rets) > 1 else 0.03)
    hi90 = max(closes[-90:])
    return {"price": last, "rsi14": rsi(closes), "ema20": ema(closes[-60:], 20), "ema50": ema(closes[-120:], 50),
            "chg7": round((last / closes[-8] - 1) * 100, 1) if len(closes) > 8 else 0.0,
            "chg30": round((last / closes[-31] - 1) * 100, 1) if len(closes) > 31 else 0.0,
            "vol30_ann": round(vol * math.sqrt(365) * 100, 1), "drawdown90": round((last / hi90 - 1) * 100, 1),
            "daily_vol": vol, "drift": statistics.fmean(rets[-90:]) if rets else 0.0}


@dataclass(frozen=True)
class Signal:
    """One rule-based argument: the plain-English point and the number that backs it.

    Points and evidence are created together, so a point can never be paired with
    another point's data (QA 3 Nov: the fake debate zipped two fixed lists by position)."""
    point: str
    evidence: str

    def as_dict(self) -> dict:
        return {"point": self.point, "evidence": self.evidence}


# Always-true context used to fill a side to 3 points when the indicators give fewer.
_BULL_FILLERS = (
    Signal("One of the largest coins by market value, so it trades a lot every day.", "Rank #{rank} by market size"),
    Signal("Steady buyers through past cycles have been rewarded over the long run.", "Past 4-year cycles"),
    Signal("Regular monthly buying smooths out the jumps.", "Rupee-cost averaging"),
)
_BEAR_FILLERS = (
    Signal("Crypto can fall 30–50% even in good years.", "Yearly volatility {vol30_ann}%"),
    Signal("News and big-holder selling can move the price fast.", "Unregulated market"),
    Signal("There is no investor protection if an exchange fails.", "Crypto is unregulated in India"),
)


def signals(ind: dict, rank: Optional[int] = None) -> tuple[int, list[Signal], list[Signal]]:
    """Score (−4…+3) plus bull and bear signals (3 each, most specific first)."""
    s = 0
    bull: list[Signal] = []
    bear: list[Signal] = []
    trend_ev = f"20-day avg {ind['ema20']:.4g} vs 50-day {ind['ema50']:.4g}"
    if ind["ema20"] > ind["ema50"]:
        s += 1
        bull.append(Signal("Short-term trend is above the longer trend (20-day average over 50-day).", trend_ev))
    else:
        s -= 1
        bear.append(Signal("Short-term trend is below the longer trend (20-day average under 50-day).", trend_ev))
    chg_ev = f"30-day change {ind['chg30']}%"
    if ind["chg30"] > 5:
        s += 1
        bull.append(Signal(f"Up {ind['chg30']}% over 30 days — buyers are in control.", chg_ev))
    elif ind["chg30"] < -5:
        s -= 1
        bear.append(Signal(f"Down {abs(ind['chg30'])}% over 30 days — sellers are in control.", chg_ev))
    r = ind["rsi14"]
    rsi_ev = f"RSI {r}"
    if r > 72:
        s -= 1
        bear.append(Signal(f"RSI {r}: overheated — pullbacks are common from here.", rsi_ev))
    elif r < 30:
        s += 1
        bull.append(Signal(f"RSI {r}: oversold — bounces often start near here.", rsi_ev))
    elif r >= 50:
        bull.append(Signal(f"RSI {r}: momentum is positive but not extreme.", rsi_ev))
    else:
        bear.append(Signal(f"RSI {r}: momentum is weak but not extreme.", rsi_ev))
    dd_ev = f"{ind['drawdown90']}% from the 90-day high"
    if ind["drawdown90"] < -25:
        bear.append(Signal(f"{abs(ind['drawdown90'])}% below its 90-day high.", dd_ev))
        bull.append(Signal("A deep fall can mean better long-term entry prices for steady buyers.", dd_ev))
    if ind["vol30_ann"] > 90:
        bear.append(Signal(f"Very jumpy: about {ind['vol30_ann']:.0f}% yearly volatility.", f"Yearly volatility {ind['vol30_ann']}%"))
    ctx = {"rank": rank or "—", "vol30_ann": ind["vol30_ann"]}
    for side, fillers in ((bull, _BULL_FILLERS), (bear, _BEAR_FILLERS)):
        for f in fillers:
            if len(side) >= 3:
                break
            side.append(Signal(f.point, f.evidence.format(**ctx)))
    return s, bull[:3], bear[:3]


def rule_verdict(ind: dict, rank: Optional[int] = None) -> tuple[str, int, list[Signal], list[Signal]]:
    s, bull, bear = signals(ind, rank)
    verdict = "Bullish" if s >= 2 else "Bearish" if s <= -2 else "Neutral"
    conf = min(85, 50 + abs(s) * 9)
    return verdict, conf, bull, bear


# ------------------------------------------------------------------ daily job ----
async def committee(sym: str, name: str, ind: dict) -> dict:
    v, conf, bull_s, bear_s = rule_verdict(ind)
    bull, bear = [x.point for x in bull_s], [x.point for x in bear_s]

    def fake():
        return {"bull": bull, "bear": bear, "verdict": v, "confidence": conf,
                "summary": {"Bullish": f"{name} looks strong for now; buyers have the edge.",
                            "Bearish": f"{name} is weak for now; let it settle before adding.",
                            "Neutral": f"{name} is undecided; no strong edge either way."}[v],
                "chair": f"{v} with {conf}% confidence. {bull[0] if v != 'Bearish' else bear[0]}"}
    sys = ("You are a crypto research committee for Indian beginners: a bull analyst, a bear analyst and a chair. "
           "Use only the data given. Plain English, short sentences, no price targets, no 'buy'/'sell' instructions.")
    prompt = (f"Coin: {name} ({sym}). Data (USD): price {ind['price']:.4g}, RSI14 {ind['rsi14']}, EMA20 {ind['ema20']:.4g}, "
              f"EMA50 {ind['ema50']:.4g}, 7d {ind['chg7']}%, 30d {ind['chg30']}%, yearly volatility {ind['vol30_ann']}%, "
              f"from 90-day high {ind['drawdown90']}%.\nReturn {{\"bull\": [3 short points], \"bear\": [3 short points], "
              '"verdict": "Bullish|Neutral|Bearish", "confidence": 0-100, "summary": one line, "chair": two sentences}.')
    # made_by: "ai" when the model's answer is used, "rules" when the backup wording is (no key, AI error, bad reply),
    # so the page never calls a rule-made verdict an AI committee's (QA 10 Nov).
    try:
        out = await llm.complete_json(task="committee", system=sys, prompt=prompt, fake=fake, model="strong")
        made_by = "rules" if llm.mode() == "fake" else "ai"
        if out.get("verdict") not in ("Bullish", "Neutral", "Bearish"):
            out, made_by = fake(), "rules"
    except llm.LLMError:
        out, made_by = fake(), "rules"
    return {**out, "made_by": made_by}


async def job_daily(ctx) -> dict:
    if not is_on("CRYPTO_COMMITTEE"):
        return {"status": "off"}
    d = ctx.db
    day = ctx.now.astimezone(IST).date().isoformat()
    coins = await market.top_coins(10)
    # The start price for hit-rate scoring comes from the same price source the scoring job reads later
    # (Twelve Data when configured), not from the market-cap list.
    live = await market.prices([c["symbol"] for c in coins]) if coins else {}
    done = changed = 0
    for c in coins:
        sym = c["symbol"]
        hist = await market.history(sym, 150)
        closes = [p for _, p in hist]
        if len(closes) < 60:
            continue
        ind = indicators(closes)
        out = await committee(sym, c["name"], ind)
        prev = await d.verdicts.find_one({"symbol": sym, "date": {"$lt": day}}, sort=[("date", -1)])
        changed_from = prev["verdict"] if prev and prev["verdict"] != out["verdict"] else None
        doc = {"_id": f"{day}:{sym}", "date": day, "symbol": sym, "name": c["name"], "rank": c.get("rank"),
               "verdict": out["verdict"], "confidence": int(out.get("confidence") or 50),
               "summary": out.get("summary"), "bull": out.get("bull", [])[:3], "bear": out.get("bear", [])[:3],
               "chair": out.get("chair"),
               "price_usd": (live.get(sym) or {}).get("price_usd") or c.get("price_usd"),
               "price_source": (live.get(sym) or {}).get("source") or market.price_source(),
               "indicators": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in ind.items()},
               "changed_from": changed_from, "made_by": out.get("made_by", "rules"), "created_at": ctx.now}
        await d.verdicts.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        done += 1
        if changed_from:
            changed += 1
            from notify.service import alert_many   # bulk: thousands of watchers per coin at 05:30
            watchers = [w["_id"] async for w in d.watchlists.find({"symbols": sym}, {"_id": 1})]
            await alert_many(d, watchers, "verdict_changed", f"{sym} verdict changed: {changed_from} → {out['verdict']}",
                             out.get("summary") or "", link=f"/app/coin/{sym}", dedupe=f"vc:{day}:{sym}")
    # A coin that dropped out of the list keeps its earlier entry for the same day; remove it so a re-run
    # ("Run now") replaces the whole list (QA 10 Nov: FIGR_HELOC stayed after the filter changed).
    if done:
        rated = [c["symbol"] for c in coins]
        await d.verdicts.delete_many({"date": day, "symbol": {"$nin": rated}, "backtest": {"$ne": True}})
    return {"coins": done, "changed": changed, "date": day}


async def latest_date(d) -> Optional[str]:
    row = await d.verdicts.find_one({}, sort=[("date", -1)])
    return row["date"] if row else None


def shape(v: dict, details: bool, live: Optional[dict] = None, watched: bool = False) -> dict:
    out = {"symbol": v["symbol"], "name": v.get("name"),
           "price_usd": smart_round((live or {}).get("price_usd") or v.get("price_usd")),
           "change_24h": r2((live or {}).get("change_24h")), "verdict": v["verdict"], "confidence": v["confidence"],
           "changed_from": v.get("changed_from"), "summary": v.get("summary"), "watched": watched, "date": v["date"],
           "bull": None, "bear": None, "chair": None, "made_by": v.get("made_by", "rules")}
    if details:
        out.update(bull=v.get("bull"), bear=v.get("bear"), chair=v.get("chair"))
    return out


async def latest_verdict(d, symbol: str, details: bool = False) -> Optional[dict]:
    v = await d.verdicts.find_one({"symbol": symbol.upper()}, sort=[("date", -1)])
    return shape(v, details) if v else None


async def _plan_of(request: Request) -> tuple[Optional[dict], str]:
    user = await optional_user(request)
    if not user:
        return None, "free"
    return user, (await plans.effective_plan(db(), user))["plan"]


async def _watched(user: Optional[dict]) -> set[str]:
    if not user:
        return set()
    w = await db().watchlists.find_one({"_id": str(user["_id"])})
    return set((w or {}).get("symbols") or [])


@router.get("/verdicts/today")
async def today(request: Request):
    user, plan = await _plan_of(request)
    day = await latest_date(db())
    if not day:
        return {"date": None, "updated_at": None, "coins": [], "disclaimer": DISCLAIMER}
    rows = [v async for v in db().verdicts.find({"date": day}).sort("rank", 1)]
    live = await market.prices([v["symbol"] for v in rows])
    watched = await _watched(user)
    details = plans.plan_allows(plan, "verdict_details")
    if user:
        await events.track(db(), "verdicts_viewed", user_id=str(user["_id"]))
    return {"date": day, "updated_at": iso(max(v["created_at"] for v in rows)) if rows else None,
            "coins": [shape(v, details, live.get(v["symbol"]), v["symbol"] in watched) for v in rows],
            "disclaimer": DISCLAIMER}


@router.get("/verdicts/coin/{symbol}")
async def coin(symbol: str, request: Request):
    user, plan = await _plan_of(request)
    sym = symbol.upper()[:15]
    info = await market.search(sym)
    if not info:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": f"We couldn't find {sym}."})
    v = await db().verdicts.find_one({"symbol": sym}, sort=[("date", -1)])
    details = plans.plan_allows(plan, "verdict_details")
    hist = [{"date": h["date"], "verdict": h["verdict"], "confidence": h["confidence"]}
            async for h in db().verdicts.find({"symbol": sym}).sort("date", -1).limit(30)]
    return {"coin": {"symbol": info.get("symbol"), "name": info.get("name"), "rank": info.get("rank"),
                     "price_usd": smart_round(info.get("price_usd")), "change_24h": r2(info.get("change_24h")),
                     "market_cap_usd": info.get("market_cap_usd"), "ath_usd": smart_round(info.get("ath_usd")),
                     "description": info.get("description")},
            "verdict": shape(v, details, info, sym in await _watched(user)) if v else None,
            "history": hist, "disclaimer": DISCLAIMER}


# ------------------------------------------------------------------ forecast ----
class ForecastIn(BaseModel):
    symbol: str = Field(..., max_length=15)
    horizon_days: Literal[7, 30] = 7


async def _kronos(sym: str, hist: list[tuple[str, float]], horizon: int) -> Optional[list[float]]:
    import os
    if vendor_mode("kronos") != "live":
        return None
    bars = [{"timestamp": d + "T00:00:00Z", "open": p, "high": p, "low": p, "close": p, "volume": 0} for d, p in hist[-400:]]
    try:
        async with httpx.AsyncClient(timeout=85) as c:
            r = await c.post(os.environ["KRONOS_API_URL"], headers={"x-api-key": os.environ["KRONOS_API_KEY"]},
                             json={"symbol": f"{sym}-USD", "history": bars, "pred_len": horizon, "samples": 6})
            r.raise_for_status()
            path = r.json().get("expected_path")
            return [float(x) for x in path][:horizon] if path else None
    except Exception:  # noqa: BLE001 — fall back to the statistical band
        return None


def statistical_path(last: float, drift: float, vol: float, horizon: int, kronos: Optional[list[float]] = None) -> list[dict]:
    mu = max(-0.004, min(0.004, drift * 0.5))     # shrink the trend: crypto momentum fades
    out = []
    for t in range(1, horizon + 1):
        mid = kronos[t - 1] if kronos and len(kronos) >= t else last * math.exp(mu * t)
        band = 1.2816 * vol * math.sqrt(t)          # 80% range
        out.append({"day": t, "price_usd": smart_round(mid), "low_usd": smart_round(mid * math.exp(-band)),
                    "high_usd": smart_round(mid * math.exp(band))})
    return out


async def forecast_for(sym: str, horizon: int) -> dict:
    hist = await market.history(sym, 400)
    if len(hist) < 60:
        raise HTTPException(status_code=404, detail={"code": "no_history", "msg": f"Not enough price history for {sym}."})
    closes = [p for _, p in hist]
    ind = indicators(closes)
    live = (await market.prices([sym])).get(sym, {})
    last = live.get("price_usd") or closes[-1]
    kr = await _kronos(sym, hist, horizon)
    path = statistical_path(last, ind["drift"], ind["daily_vol"], horizon, kr)
    end = path[-1]
    return {"symbol": sym, "horizon_days": horizon, "last_price_usd": smart_round(last),
            "expected_price_usd": end["price_usd"], "low_usd": end["low_usd"], "high_usd": end["high_usd"],
            "expected_move_pct": round((end["price_usd"] / last - 1) * 100, 1), "path": path,
            "model": "kronos" if kr else "statistical", "as_of": iso(utcnow()),
            "disclaimer": "A model's range for where the price may land (80% of outcomes), not a target. " + DISCLAIMER}


@router.post("/verdicts/forecast")
async def forecast(body: ForecastIn, user: dict = Depends(user_dep())):
    plan = await plans.require(db(), user, "forecast")
    usage = await plans.consume(db(), user, "forecast", plan)
    try:
        out = await forecast_for(body.symbol.upper(), body.horizon_days)
    except HTTPException:
        await plans.refund(db(), user, "forecast")
        raise
    await events.track(db(), "forecast_run", user_id=str(user["_id"]), props={"symbol": body.symbol.upper(), "horizon": body.horizon_days})
    return {**out, "usage": usage}


# ------------------------------------------------------------------ debate ----
class DebateIn(BaseModel):
    symbol: str = Field(..., max_length=15)


def _valid_debate(out) -> Optional[dict]:
    """A model reply is used only if both sides have 3 {point, evidence} strings and the chair verdict is known;
    anything else falls back to the rule-based debate rather than showing a lopsided or half-empty screen."""
    if not isinstance(out, dict):
        return None
    for side in ("bull", "bear"):
        items = out.get(side)
        if not isinstance(items, list) or len(items) < 3:
            return None
        if not all(isinstance(i, dict) and str(i.get("point") or "").strip() and str(i.get("evidence") or "").strip()
                   for i in items[:3]):
            return None
    chair = out.get("chair")
    if not isinstance(chair, dict) or chair.get("verdict") not in ("Bullish", "Neutral", "Bearish"):
        return None
    return out


async def debate_for(sym: str) -> dict:
    hist = await market.history(sym, 150)
    if len(hist) < 60:
        raise HTTPException(status_code=404, detail={"code": "no_history", "msg": f"Not enough price history for {sym}."})
    info = await market.search(sym) or {"name": sym}
    ind = indicators([p for _, p in hist])
    v, conf, bull, bear = rule_verdict(ind, info.get("rank"))

    def fake():
        return {"bull": [x.as_dict() for x in bull], "bear": [x.as_dict() for x in bear],
                "chair": {"verdict": v, "confidence": conf,
                          "call": f"On balance {v.lower()}. {'The trend supports buyers' if v == 'Bullish' else 'Wait for the trend to improve' if v == 'Bearish' else 'Neither side has a clear edge'}; size any buy so a 40% fall wouldn't hurt."}}
    sys = ("Run a debate on one crypto coin for Indian beginners: bull analyst (3 points), bear analyst (3 points), then a chair "
           "who weighs both. Each point has short evidence from the data. Plain English. No price targets, no instructions to buy or sell.")
    prompt = (f"{info.get('name')} ({sym}). Data: price ${ind['price']:.4g}, RSI14 {ind['rsi14']}, 7d {ind['chg7']}%, 30d {ind['chg30']}%, "
              f"EMA20 {ind['ema20']:.4g} vs EMA50 {ind['ema50']:.4g}, yearly volatility {ind['vol30_ann']}%, "
              f"from 90-day high {ind['drawdown90']}%, market cap rank {info.get('rank')}.\n"
              'Return {"bull": [{"point", "evidence"}], "bear": [{"point", "evidence"}], "chair": {"verdict": "Bullish|Neutral|Bearish", "confidence": 0-100, "call": str}}.')
    made_by = "rules"
    try:
        got = _valid_debate(await llm.complete_json(task="debate", system=sys, prompt=prompt, fake=fake, model="strong",
                                                    max_tokens=4000))
        out, made_by = (got, "ai" if llm.mode() != "fake" else "rules") if got else (fake(), "rules")
    except llm.LLMError:
        out = fake()
    return {"symbol": sym, "bull": out.get("bull", [])[:3], "bear": out.get("bear", [])[:3], "chair": out.get("chair"),
            "made_by": made_by, "as_of": iso(utcnow()), "disclaimer": DISCLAIMER}


@router.post("/verdicts/debate")
async def debate(body: DebateIn, user: dict = Depends(user_dep())):
    plan = await plans.require(db(), user, "debate")
    usage = await plans.consume(db(), user, "debate", plan)
    try:
        out = await debate_for(body.symbol.upper())
    except HTTPException:
        await plans.refund(db(), user, "debate")
        raise
    await events.track(db(), "debate_run", user_id=str(user["_id"]), props={"symbol": body.symbol.upper()})
    return {**out, "usage": usage}


# ------------------------------------------------------------------ pulse ----
def cycle(today: date, btc_price: Optional[float], ath: Optional[float]) -> dict:
    last = max(h for h in HALVINGS if h <= today)
    since = (today - last).days
    span = (NEXT_HALVING_EST - last).days
    months = since / 30.44
    if months < 6:
        phase, note = "Post-halving build-up", "In past cycles prices often moved sideways for months after the halving."
    elif months < 18:
        phase, note = "Expansion", "In past cycles this was the strongest stretch — and where the cycle top formed."
    elif months < 30:
        phase, note = "Late cycle", "In past cycles the top came around 12–18 months after the halving; big falls followed."
    else:
        phase, note = "Cool-off & accumulation", ("In past cycles this stretch had the deepest falls and the best long-term "
                                                   "entry prices for steady buyers.")
    dd = round((btc_price / ath - 1) * 100, 1) if btc_price and ath else None
    return {"last_halving": last.isoformat(), "next_halving_est": NEXT_HALVING_EST.strftime("%Y-%m"),
            "days_since": since, "days_to_next": (NEXT_HALVING_EST - today).days, "phase": phase,
            "phase_note": note + " Past cycles don't guarantee the next one.", "ath_usd": smart_round(ath),
            "drawdown_from_ath_pct": dd, "position_pct": round(min(100.0, since / span * 100), 1)}


async def _btc_ath() -> Optional[float]:
    try:
        return await market.ath_usd("BTC")
    except Exception:  # noqa: BLE001 — the cycle meter still works without the high
        return None


async def build_pulse(d) -> dict:
    syms = ["BTC", "ETH", "SOL", "XRP"]
    px = await market.prices(syms)
    fx, _ = await usd_inr(d)
    g = await market.global_stats()
    fg = await market.fear_greed()
    etf = await d.etf_flows.find_one({}, sort=[("date", -1)])
    btc = px.get("BTC", {})
    return {"coins": [{"symbol": s, "price_usd": smart_round(px[s]["price_usd"]),
                       "price_inr": round(px[s]["price_usd"] * fx, 2), "change_24h": r2(px[s].get("change_24h"))}
                      for s in syms if s in px],
            "total_mcap_usd": g.get("total_mcap_usd"), "btc_dominance_pct": r2(g.get("btc_dominance_pct"), 1),
            "fear_greed": fg,
            "etf_flows": {"date": etf["date"], "net_usd_m": etf["net_usd_m"], "note": etf.get("note")} if etf else None,
            "cycle": cycle(utcnow().astimezone(IST).date(), btc.get("price_usd"), btc.get("ath_usd") or await _btc_ath()),
            "as_of": iso(utcnow())}


@router.get("/public/pulse")
async def public_pulse():
    return await build_pulse(db())


@router.get("/pulse")
async def pulse(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "pulse")
    return await build_pulse(db())


# ------------------------------------------------------------------ watchlist ----
@router.get("/watchlist")
async def watchlist(user: dict = Depends(user_dep())):
    return {"symbols": sorted(await _watched(user))}


@router.post("/watchlist/{symbol}")
async def watch(symbol: str, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "watchlist")
    sym = symbol.upper()[:15]
    if not await market.search(sym):
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": f"We couldn't find {sym}."})
    w = await db().watchlists.find_one({"_id": str(user["_id"])}) or {}
    if len(w.get("symbols") or []) >= 30 and sym not in w.get("symbols", []):
        raise HTTPException(status_code=400, detail={"code": "too_many", "msg": "Your watchlist holds up to 30 coins."})
    await db().watchlists.update_one({"_id": str(user["_id"])}, {"$addToSet": {"symbols": sym}}, upsert=True)
    await events.track(db(), "watchlist_added", user_id=str(user["_id"]), props={"symbol": sym})
    return {"symbols": sorted(await _watched(user))}


@router.delete("/watchlist/{symbol}")
async def unwatch(symbol: str, user: dict = Depends(user_dep())):
    await db().watchlists.update_one({"_id": str(user["_id"])}, {"$pull": {"symbols": symbol.upper()}})
    await events.track(db(), "watchlist_removed", user_id=str(user["_id"]), props={"symbol": symbol.upper()})
    return {"symbols": sorted(await _watched(user))}


# ------------------------------------------------------------------ Monday picks ----
def week_of(d: Optional[date] = None) -> str:
    d = d or utcnow().astimezone(IST).date()
    return (d - timedelta(days=d.weekday())).isoformat()


@router.get("/picks/monday")
async def monday(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "monday_picks")
    if not is_on("MONDAY_PICKS"):
        return {"week_of": None, "published": False, "picks": [], "disclaimer": DISCLAIMER}
    p = await db().picks.find_one({"published": True}, sort=[("_id", -1)])
    if not p:
        return {"week_of": None, "published": False, "picks": [], "disclaimer": DISCLAIMER}
    live = await market.prices([x["symbol"] for x in p["picks"]])
    out = []
    for x in p["picks"]:
        now = (live.get(x["symbol"]) or {}).get("price_usd")
        at = x.get("price_at_pick_usd")
        out.append({"symbol": x["symbol"], "name": x.get("name"), "verdict": x.get("verdict"),
                    "confidence": x.get("confidence"), "reasoning": x.get("reasoning"),
                    "price_at_pick_usd": smart_round(at), "price_now_usd": smart_round(now),
                    "change_pct": round((now / at - 1) * 100, 1) if now and at else None})
    return {"week_of": p["_id"], "published": True, "picks": out, "disclaimer": DISCLAIMER}


async def suggest_picks(d) -> list[dict]:
    day = await latest_date(d)
    if not day:
        return []
    rows = [v async for v in d.verdicts.find({"date": day, "verdict": "Bullish"}).sort("confidence", -1).limit(2)]
    if len(rows) < 2:
        rows += [v async for v in d.verdicts.find({"date": day, "verdict": "Neutral"}).sort("confidence", -1).limit(2 - len(rows))]
    return [{"symbol": v["symbol"], "name": v.get("name"), "verdict": v["verdict"], "confidence": v["confidence"],
             "reasoning": (v.get("summary") or "") + " " + " ".join((v.get("bull") or [])[:2])} for v in rows]
