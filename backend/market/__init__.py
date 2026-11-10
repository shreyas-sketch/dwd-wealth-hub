"""Crypto market data behind one interface (live public APIs or a deterministic fake).

Live sources:
  Twelve Data      prices and daily price history, when TWELVE_DATA_API_KEY is set (market/twelvedata.py).
                   MARKET_PRICE_SOURCE=coingecko|twelvedata forces one; any coin Twelve Data can't give (unknown
                   pair, out of credits, error) is fetched from CoinGecko instead, so a page never goes blank.
  CoinGecko v3     everything Twelve Data doesn't have: top coins by market cap, search and coin details,
                   contract lookup, market totals, trending (and prices/history when Twelve Data is off)
  alternative.me   Fear & Greed index
  Binance / KuCoin spot symbol lists (Early Coin Radar's new-listing diff)

`vendor_mode("market")`: live by default, fake in QA_MODE/tests, never fake in production.
Every call is cached in-process (prices 60 s, history 6 h, lists 1 h).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

from core.vendors import vendor_mode

log = logging.getLogger("market")

_cache: dict[str, tuple[float, Any]] = {}
_provider = {"obj": None, "mode": None}
_td: dict = {"obj": None, "key": None}

STABLES = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "USDS", "PYUSD", "USD1", "RLUSD", "BUSD", "USDD", "FRAX",
           "LUSD", "GHO", "CRVUSD", "SUSDE", "EURC", "EURT"}


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


def price_source() -> str:
    """Where prices and price history come from: "fake" (QA/tests), "twelvedata" or "coingecko"."""
    if vendor_mode("market") == "fake":
        return "fake"
    key = os.environ.get("TWELVE_DATA_API_KEY", "")
    want = (os.environ.get("MARKET_PRICE_SOURCE") or "").strip().lower()
    if want == "coingecko":
        return "coingecko"
    if want == "twelvedata" and not key:
        log.warning("MARKET_PRICE_SOURCE=twelvedata but TWELVE_DATA_API_KEY is empty; using CoinGecko")
        return "coingecko"
    return "twelvedata" if key else "coingecko"


def td_provider():
    key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if _td["obj"] is None or _td["key"] != key:
        from .twelvedata import TwelveDataMarket
        _td["obj"], _td["key"] = TwelveDataMarket(key), key
    return _td["obj"]


async def _fetch_prices(syms: list[str]) -> dict[str, dict]:
    if price_source() != "twelvedata":
        return await provider().prices(syms)
    got: dict[str, dict] = {}
    try:
        got = await td_provider().prices(syms)
    except Exception as e:  # noqa: BLE001 — out of credits, bad key, network: CoinGecko fills in
        log.info("Twelve Data prices failed (%s); using CoinGecko for %s", e, ",".join(syms))
    rest = [s for s in syms if s not in got]
    if rest:
        try:
            filled = await provider().prices(rest)
            got = {**got, **{k: {**v, "source": v.get("source") or "coingecko"} for k, v in filled.items()}}
        except Exception:
            if not got:
                raise
    return got


async def _fetch_history(symbol: str, days: int) -> list[tuple[str, float]]:
    if price_source() == "twelvedata":
        try:
            rows = await td_provider().history(symbol, days)
            if rows:
                return rows
        except Exception as e:  # noqa: BLE001
            log.info("Twelve Data history %s failed (%s); using CoinGecko", symbol, e)
    return await provider().history(symbol, days)


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
    _td["obj"] = None


# Not coins a beginner gets a daily call on: wrapped or staked versions of another coin, tokenised gold, funds and
# loans. (QA 10 Nov: "Figure Heloc", a tokenised home-equity loan, was in the daily top 10.)
NOT_COINS = {"WBTC", "WETH", "STETH", "WSTETH", "WEETH", "EETH", "CBBTC", "CBETH", "RETH", "METH", "BETH", "EZETH",
             "RSETH", "SFRXETH", "TBTC", "LBTC", "SOLVBTC", "BTCB", "JITOSOL", "MSOL", "BNSOL", "JUPSOL", "WBETH",
             "XAUT", "PAXG", "BUIDL", "USYC", "OUSG", "USTB", "WTRX", "WBNB", "WAVAX", "WSOL", "WHYPE"}


def is_plain_coin(row: dict) -> bool:
    sym = str(row.get("symbol") or "").upper()
    if not sym or not sym.isalnum():                  # FIGR_HELOC, BSC-USD, USDC.E …
        return False
    if sym in STABLES or sym in NOT_COINS or "USD" in sym:   # USDS, USD1, PYUSD …
        return False
    return True


async def top_coins(n: int = 10, exclude_stables: bool = True, tradable: bool = True) -> list[dict]:
    """The n largest coins by market value that are real coins and, with `tradable`, have a USDT pair on Binance or
    KuCoin (what the app's buy features use). If the exchange lists can't be read, that check is skipped rather than
    leaving the list empty."""
    rows = await _cached(f"top:{n + 30}", 120, lambda: provider().top_coins(n + 30))
    if exclude_stables:
        rows = [r for r in rows if is_plain_coin(r)]
    if tradable:
        listed: set[str] = set()
        for venue in ("binance", "kucoin"):
            try:
                listed |= set(await listings(venue))
            except Exception:  # noqa: BLE001
                pass
        if listed:
            rows = [r for r in rows if r["symbol"] in listed]
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
            got = await _cached("px:" + ",".join(missing), PRICE_TTL, lambda: _fetch_prices(missing))
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
    return await _cached(f"hist:{symbol.upper()}:{days}", 6 * 3600, lambda: _fetch_history(symbol.upper(), days))


async def ath_usd(symbol: str) -> Optional[float]:
    """Highest daily close in the last ~5½ years, for sources that don't report an all-time high (Twelve Data).
    A daily close is a little below the intraday peak, which is fine for "x% below its high"."""
    rows = await history(symbol, 2000)
    return max((p for _, p in rows), default=None)


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
