"""Live market data from public APIs. Written against the providers' public docs.

# NEEDS: run once with network to confirm response shapes (no key needed for any of these).
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from core.http import RateLimited, TokenBucket, shared_client, wait_budget

log = logging.getLogger("market.live")

CG = os.environ.get("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3").rstrip("/")
FNG = "https://api.alternative.me/fng/?limit=1"
BINANCE_INFO = "https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT"
# Binance's public market-data host. api.binance.com refuses requests from US servers (HTTP 451), which is where
# Railway runs; this host serves the same exchangeInfo for market data only. QA 11 Nov.
BINANCE_INFO_FALLBACK = "https://data-api.binance.vision/api/v3/exchangeInfo?permissions=SPOT"
KUCOIN_SYMBOLS = "https://api.kucoin.com/api/v2/symbols"

IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple", "BNB": "binancecoin",
       "DOGE": "dogecoin", "ADA": "cardano", "TRX": "tron", "AVAX": "avalanche-2", "LINK": "chainlink",
       "TON": "the-open-network", "DOT": "polkadot", "POL": "polygon-ecosystem-token", "SHIB": "shiba-inu",
       "LTC": "litecoin", "USDT": "tether", "USDC": "usd-coin", "SUI": "sui", "PEPE": "pepe", "WIF": "dogwifcoin",
       "BONK": "bonk", "NEAR": "near", "APT": "aptos", "ARB": "arbitrum", "OP": "optimism", "UNI": "uniswap"}
PLATFORMS = {"ethereum": "ethereum", "bsc": "binance-smart-chain", "solana": "solana", "polygon": "polygon-pos",
             "base": "base", "arbitrum": "arbitrum-one"}
_EVM = re.compile(r"^0x[a-fA-F0-9]{40}$")
_SOL = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _headers() -> dict:
    key = os.environ.get("COINGECKO_API_KEY")
    if not key:
        return {"accept": "application/json"}
    hdr = "x-cg-pro-api-key" if "pro-api" in CG else "x-cg-demo-api-key"
    return {"accept": "application/json", hdr: key}


def _cg_rate() -> float:
    """CoinGecko calls per minute this worker may make. Free/demo tier allows ~30/min per IP, shared by all workers,
    so the default leaves room for 2 workers; set COINGECKO_RATE_PER_MIN for a paid key (e.g. 400)."""
    try:
        return max(1.0, float(os.environ.get("COINGECKO_RATE_PER_MIN", "") or (400 if "pro-api" in CG else 12)))
    except ValueError:
        return 12.0


# One budget per worker for every CoinGecko call. When it's used up, calls fail fast with RateLimited and
# market._cached serves the last good value (stale-while-error), instead of CoinGecko answering 429 for everyone.
CG_BUCKET = TokenBucket(_cg_rate(), 60.0, name="coingecko")
_ID_TTL, _ID_MISS_TTL = 24 * 3600, 3600
_ids: dict[str, tuple[float, Optional[str]]] = {}      # symbol → (at, coingecko id | None), so prices() skips /search


def _row(m: dict) -> dict:
    return {"id": m.get("id"), "symbol": (m.get("symbol") or "").upper(), "name": m.get("name"),
            "rank": m.get("market_cap_rank"), "price_usd": m.get("current_price"),
            "market_cap_usd": m.get("market_cap"), "volume_24h_usd": m.get("total_volume"),
            "change_24h": m.get("price_change_percentage_24h"), "ath_usd": m.get("ath"), "image": m.get("image")}


class LiveMarket:
    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client

    async def _get(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None):
        is_cg = url.startswith(CG)
        if is_cg:
            await CG_BUCKET.acquire(wait_budget(float(os.environ.get("COINGECKO_MAX_WAIT_S", "4") or 4)))
        c = self._client or shared_client()
        r = await c.get(url, params=params, headers=headers or _headers(), timeout=15)
        if is_cg and r.status_code == 429:
            try:
                wait = float(r.headers.get("retry-after") or 60)
            except ValueError:
                wait = 60.0
            CG_BUCKET.cool_down(min(wait, 300))
            raise RateLimited("coingecko answered 429")
        r.raise_for_status()
        return r.json()

    async def _id_for(self, symbol: str) -> Optional[str]:
        if symbol in IDS:
            return IDS[symbol]
        hit = _ids.get(symbol)
        if hit and time.time() - hit[0] < (_ID_TTL if hit[1] else _ID_MISS_TTL):
            return hit[1]
        d = await self._get(f"{CG}/search", {"query": symbol})
        found = next((c["id"] for c in d.get("coins", []) if (c.get("symbol") or "").upper() == symbol), None)
        if len(_ids) > 5000:
            _ids.clear()
        _ids[symbol] = (time.time(), found)
        return found

    async def top_coins(self, n: int) -> list[dict]:
        d = await self._get(f"{CG}/coins/markets", {"vs_currency": "usd", "order": "market_cap_desc",
                                                    "per_page": min(n, 250), "page": 1,
                                                    "price_change_percentage": "24h"})
        return [_row(m) for m in d]

    async def prices(self, symbols: list[str]) -> dict[str, dict]:
        ids = {}
        for s in symbols:
            i = await self._id_for(s)
            if i:
                ids[i] = s
        if not ids:
            return {}
        d = await self._get(f"{CG}/coins/markets", {"vs_currency": "usd", "ids": ",".join(ids),
                                                    "price_change_percentage": "24h"})
        out = {}
        for m in d:
            r = _row(m)
            out[ids.get(m["id"], r["symbol"])] = r
        return out

    async def history(self, symbol: str, days: int) -> list[tuple[str, float]]:
        cid = await self._id_for(symbol)
        if not cid:
            return []
        d = await self._get(f"{CG}/coins/{cid}/market_chart", {"vs_currency": "usd", "days": days, "interval": "daily"})
        out: dict[str, float] = {}
        for ts, px in d.get("prices", []):
            out[datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()] = float(px)
        return sorted(out.items())

    async def _detail(self, cid: str) -> Optional[dict]:
        m = await self._get(f"{CG}/coins/{cid}", {"localization": "false", "tickers": "false", "market_data": "true",
                                                  "community_data": "false", "developer_data": "false"})
        md = m.get("market_data") or {}
        platforms = {k: v for k, v in (m.get("platforms") or {}).items() if k and v}
        chain, contract = (next(iter(platforms.items())) if platforms else (m.get("asset_platform_id"), None))
        genesis = m.get("genesis_date")
        return {"id": m.get("id"), "symbol": (m.get("symbol") or "").upper(), "name": m.get("name"),
                "rank": m.get("market_cap_rank"), "price_usd": (md.get("current_price") or {}).get("usd"),
                "market_cap_usd": (md.get("market_cap") or {}).get("usd"),
                "volume_24h_usd": (md.get("total_volume") or {}).get("usd"),
                "change_24h": md.get("price_change_percentage_24h"), "ath_usd": (md.get("ath") or {}).get("usd"),
                "chain": chain, "contract": contract, "genesis_date": genesis,
                "categories": m.get("categories") or [],
                "description": ((m.get("description") or {}).get("en") or "")[:1200],
                "homepage": ((m.get("links") or {}).get("homepage") or [None])[0]}

    async def search(self, query: str) -> Optional[dict]:
        q = query.strip()
        if _EVM.match(q) or (_SOL.match(q) and not q.isalpha()):
            plats = ["ethereum", "binance-smart-chain", "base", "polygon-pos", "arbitrum-one"] if _EVM.match(q) else ["solana"]
            for p in plats:
                try:
                    m = await self._get(f"{CG}/coins/{p}/contract/{q}")
                    return await self._detail(m["id"])
                except httpx.HTTPError:
                    continue
            return {"symbol": None, "name": None, "contract": q, "chain": plats[0], "unlisted": True}
        sym = q.upper()
        cid = IDS.get(sym)
        if not cid:
            d = await self._get(f"{CG}/search", {"query": q})
            coins = d.get("coins") or []
            exact = [c for c in coins if (c.get("symbol") or "").upper() == sym or (c.get("name") or "").lower() == q.lower()]
            pick = (exact or coins or [None])[0]
            cid = pick["id"] if pick else None
        return await self._detail(cid) if cid else None

    async def global_stats(self) -> dict:
        d = (await self._get(f"{CG}/global")).get("data") or {}
        return {"total_mcap_usd": (d.get("total_market_cap") or {}).get("usd"),
                "btc_dominance_pct": (d.get("market_cap_percentage") or {}).get("btc")}

    async def fear_greed(self) -> dict:
        d = (await self._get(FNG, headers={"accept": "application/json"})).get("data") or [{}]
        return {"value": int(d[0].get("value", 50)), "label": d[0].get("value_classification", "Neutral")}

    async def trending(self) -> list[dict]:
        d = await self._get(f"{CG}/search/trending")
        out = []
        for c in d.get("coins", [])[:10]:
            it = c.get("item") or {}
            data = it.get("data") or {}
            out.append({"symbol": (it.get("symbol") or "").upper(), "name": it.get("name"), "id": it.get("id"),
                        "rank": it.get("market_cap_rank"), "price_usd": data.get("price"),
                        "change_24h": (data.get("price_change_percentage_24h") or {}).get("usd")})
        return out

    async def listings(self, venue: str) -> list[str]:
        if venue == "binance":
            try:
                d = await self._get(BINANCE_INFO, headers={"accept": "application/json"})
            except Exception as e:  # noqa: BLE001 — geo-blocked or down: try the market-data host
                log.info("binance exchangeInfo failed (%s); using %s", type(e).__name__, BINANCE_INFO_FALLBACK)
                d = await self._get(BINANCE_INFO_FALLBACK, headers={"accept": "application/json"})
            return sorted({s["baseAsset"] for s in d.get("symbols", [])
                           if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"})
        if venue == "kucoin":
            d = await self._get(KUCOIN_SYMBOLS, headers={"accept": "application/json"})
            return sorted({s["baseCurrency"] for s in d.get("data", [])
                           if s.get("quoteCurrency") == "USDT" and s.get("enableTrading")})
        return []
