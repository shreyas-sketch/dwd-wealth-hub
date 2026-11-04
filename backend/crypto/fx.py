"""USD→INR rate (from Bullzeye crypto/fx.py; CoinGecko added as a keyless source).

Order: Twelve Data USD/INR (TWELVE_DATA_API_KEY) → CoinGecko USDT/INR (no key) → USDINR_FALLBACK (default 88.0).
Cached per IST day in `fx_rates`; the source is stored so a CA can see it.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import httpx

from growth.clock import IST, as_utc, utcnow


_fail = {"at": 0.0}


async def _live() -> Optional[tuple[float, str]]:
    import time
    from core.vendors import vendor_mode
    if vendor_mode("market") != "live" or time.time() - _fail["at"] < 600:
        return None
    out = await _fetch()
    if out is None:
        _fail["at"] = time.time()
    return out


async def _fetch() -> Optional[tuple[float, str]]:
    key = os.environ.get("TWELVE_DATA_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if key:
                r = await c.get("https://api.twelvedata.com/price", params={"symbol": "USD/INR", "apikey": key})
                v = float(r.json()["price"])
                if 60 < v < 150:
                    return v, "twelvedata"
            base = os.environ.get("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3").rstrip("/")
            r = await c.get(f"{base}/simple/price", params={"ids": "tether", "vs_currencies": "inr"})
            v = float(r.json()["tether"]["inr"])
            if 60 < v < 150:
                return v, "coingecko_usdt"
    except Exception:  # noqa: BLE001
        return None
    return None


def _fake() -> bool:
    from core.vendors import vendor_mode
    return vendor_mode("market") == "fake"


async def usd_inr(db, at: Optional[datetime] = None) -> tuple[float, str]:
    at = at or utcnow()
    day = as_utc(at).astimezone(IST).date().isoformat()
    doc = await db.fx_rates.find_one({"_id": day})
    if doc:
        return doc["rate"], doc["source"]
    got = await _live()
    rate, source = got if got else (float(os.environ.get("USDINR_FALLBACK", "88.0")), "fallback")
    if source == "fallback" and not _fake():
        return rate, source                    # don't pin a fallback for the whole day; try live again next time
    await db.fx_rates.update_one({"_id": day}, {"$setOnInsert": {"rate": rate, "source": source, "at": utcnow()}},
                                 upsert=True)
    return rate, source
