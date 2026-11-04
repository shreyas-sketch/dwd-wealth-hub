"""Crypto market data behind one interface (live public APIs or a deterministic fake).

Live sources (no keys needed; COINGECKO_API_KEY optional for higher limits):
  CoinGecko v3     prices, top coins, daily history, search, contract lookup, global, trending
  alternative.me   Fear & Greed index
  Binance / KuCoin spot symbol lists (Early Coin Radar's new-listing diff)

`vendor_mode("market")`: live by default, fake in QA_MODE/tests, never fake in production.
Every call is cached in-process (prices 60 s, history 6 h, lists 1 h).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from core.vendors import vendor_mode

_cache: dict[str, tuple[float, Any]] = {}
_provider = {"obj": None, "mode": None}

STABLES = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE"}


def provider():
    mode = vendor_mode("market")
    if _provider["obj"] is None or _provider["mode"] != mode:
        if mode == "fake":
            from .fake import FakeMarket
            _provider["obj"] = FakeMarket()
        else:
            from .live import LiveMarket
            _provider["obj"] = LiveMarket()
        _provider["mode"] = mode
        _cache.clear()
    return _provider["obj"]


_inflight: dict[str, "asyncio.Future"] = {}
_MAX_KEYS = 5000


async def _cached(key: str, ttl: float, fn):
    """In-process cache with single-flight: when 500 requests miss the same key at once (webinar spike),
    one upstream call is made and everyone awaits it. Keeps CoinGecko's free tier (~30 calls/min) safe.
    On an upstream error, a stale value (if any) is served for up to 10× the TTL."""
    hit = _cache.get(key)
    now = time.time()
    if hit and now - hit[0] < ttl:
        return hit[1]
    fut = _inflight.get(key)
    if fut is not None:
        return await asyncio.shield(fut)
    fut = asyncio.get_event_loop().create_future()
    _inflight[key] = fut
    try:
        val = await fn()
    except Exception as e:  # noqa: BLE001
        _inflight.pop(key, None)
        if hit and now - hit[0] < ttl * 10:
            fut.set_result(hit[1])
            return hit[1]
        fut.set_exception(e)
        fut.exception()              # mark retrieved: waiters re-raise it, no "never retrieved" warning
        raise
    if len(_cache) > _MAX_KEYS:      # search keys are user input: keep memory bounded
        for k in sorted(_cache, key=lambda k: _cache[k][0])[: _MAX_KEYS // 5]:
            _cache.pop(k, None)
    _cache[key] = (time.time(), val)
    _inflight.pop(key, None)
    fut.set_result(val)
    return val


def clear_cache() -> None:
    _cache.clear()
    _inflight.clear()


async def top_coins(n: int = 10, exclude_stables: bool = True) -> list[dict]:
    rows = await _cached(f"top:{n + 10}", 120, lambda: provider().top_coins(n + 10))
    if exclude_stables:
        rows = [r for r in rows if r["symbol"] not in STABLES]
    return rows[:n]


PRICE_TTL = 60


async def prices(symbols: list[str]) -> dict[str, dict]:
    """Per-coin cache: each coin's quote is cached on its own key, and only the coins missing from the cache are
    fetched, in one upstream call (single-flight per missing set). Before, every distinct combination of coins
    (a member's plan, a basket, a watchlist…) was its own cache key and its own CoinGecko call. A coin the upstream
    doesn't know is remembered as missing for the same TTL so it isn't re-requested on every page view."""
    syms = sorted({s.upper() for s in symbols if s and s.upper() not in ("USDT",)})
    out: dict[str, dict] = {}
    now = time.time()
    missing = []
    for s in syms:
        hit = _cache.get(f"px1:{s}")
        if hit and now - hit[0] < PRICE_TTL:
            if hit[1] is not None:
                out[s] = hit[1]
        else:
            missing.append(s)
    if missing:
        try:
            got = await _cached("px:" + ",".join(missing), PRICE_TTL, lambda: provider().prices(missing))
        except Exception:
            # upstream down / over budget: serve each coin's last known quote (up to 10× TTL), never re-stamped
            stale = {}
            for s in missing:
                hit = _cache.get(f"px1:{s}")
                if hit and hit[1] and now - hit[0] < PRICE_TTL * 10:
                    stale[s] = hit[1]
            if not stale and not out:
                raise
            out.update(stale)
        else:
            t = time.time()
            for s in missing:
                _cache[f"px1:{s}"] = (t, got.get(s))
                if got.get(s):
                    out[s] = got[s]
    out = dict(out)
    if any(s.upper() == "USDT" for s in symbols):
        out["USDT"] = {"symbol": "USDT", "name": "Tether", "price_usd": 1.0, "change_24h": 0.0}
    return out


async def price(symbol: str) -> Optional[float]:
    p = (await prices([symbol])).get(symbol.upper())
    return p["price_usd"] if p else None


async def history(symbol: str, days: int) -> list[tuple[str, float]]:
    """Daily closes [(YYYY-MM-DD, usd)], oldest first."""
    return await _cached(f"hist:{symbol.upper()}:{days}", 6 * 3600, lambda: provider().history(symbol.upper(), days))


async def monthly_closes(symbol: str, years: int) -> list[tuple[str, float]]:
    """[(YYYY-MM, close of the month's last day)] for the last `years` years + the current month."""
    daily = await history(symbol, years * 366 + 31)
    months: dict[str, float] = {}
    for d, px in daily:
        months[d[:7]] = px
    return list(months.items())[-(years * 12 + 1):]


async def search(query: str) -> Optional[dict]:
    q = (query or "").strip()
    return await _cached(f"search:{q.lower()}", 600, lambda: provider().search(q)) if q else None


async def global_stats() -> dict:
    return await _cached("global", 300, lambda: provider().global_stats())


async def fear_greed() -> dict:
    return await _cached("fng", 1800, lambda: provider().fear_greed())


async def trending() -> list[dict]:
    return await _cached("trending", 900, lambda: provider().trending())


async def listings(venue: str) -> list[str]:
    return await _cached(f"list:{venue}", 3600, lambda: provider().listings(venue))
