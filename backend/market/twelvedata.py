"""Twelve Data: crypto prices and daily price history (the numbers verdicts, forecasts, What If, Paper Money and the
verdict hit-rate scoring are computed from).

Checked against the live API and https://twelvedata.com/docs/llms/ on 9 Nov 2026:
  auth        header `Authorization: apikey <key>` (the docs' recommended form)
  symbols     crypto pairs as "BTC/USD"
  GET /quote          one symbol → {symbol, name: "Bitcoin US Dollar", close, previous_close, percent_change,
                      rolling_1d_change (24 h % for crypto), fifty_two_week: {...}, ...}; numbers are strings, no volume
  POST /batch         {id: {"url": "/quote?symbol=BTC/USD"}} → {"code": 200, "status": "success",
                      "data": {id: {"status": "success" | "error", "response": {...}}}}; items fail independently
  GET /time_series    interval=1day, outputsize 1–5000, order=asc → {meta, values: [{datetime, open, high, low, close}],
                      status: "ok"}
  errors      {"code", "message", "status": "error"}: 400 bad parameter / unknown symbol, 401 bad key, 403 plan,
              429 out of credits
  credits     1 per symbol for quote / time_series (a batch costs the sum). Basic (free) plan: 8 a minute, 800 a day;
              Grow: 55+ a minute. Credits are per account, shared by every server worker.

Twelve Data has no market cap, ranking, market totals, trending list, contract lookup or all-time high. Those stay
with CoinGecko (market/live.py); market/__init__.py routes each call to the right source.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

from core.http import RateLimited, TokenBucket, shared_client, wait_budget

log = logging.getLogger("market.twelvedata")

BASE = os.environ.get("TWELVE_DATA_BASE_URL", "https://api.twelvedata.com").rstrip("/")
MAX_OUTPUTSIZE = 5000
UNSUPPORTED_TTL = 24 * 3600


class TwelveDataError(RuntimeError):
    def __init__(self, code: int, msg: str):
        super().__init__(f"Twelve Data {code}: {msg}")
        self.code = code


def _budget_per_worker() -> float:
    """The account's credits a minute split across this deployment's web workers (each has its own bucket)."""
    try:
        per_min = float(os.environ.get("TWELVE_DATA_CREDITS_PER_MIN", "") or 8)
        workers = max(1, int(os.environ.get("WEB_CONCURRENCY", "") or 2))
    except ValueError:
        per_min, workers = 8.0, 2
    return max(1.0, per_min / workers)


def _bucket() -> TokenBucket:
    rate = _budget_per_worker()
    return TokenBucket(rate, 60.0, burst=rate, name="twelvedata")


BUCKET = _bucket()
_unsupported: dict[str, float] = {}           # symbol → when Twelve Data said it doesn't know it


def reset_state() -> None:
    global BUCKET
    BUCKET = _bucket()
    _unsupported.clear()


def pair(symbol: str) -> str:
    return f"{symbol.upper()}/USD"


def _num(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _row(symbol: str, q: dict) -> Optional[dict]:
    close = _num(q.get("close"))
    if close is None or close <= 0:
        return None
    change = _num(q.get("rolling_1d_change"))
    if change is None:
        change = _num(q.get("percent_change"))
    name = str(q.get("name") or symbol)
    for suffix in (" US Dollar", " / US Dollar"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return {"symbol": symbol, "name": name, "price_usd": close, "change_24h": change, "source": "twelvedata"}


def _is_unsupported(symbol: str) -> bool:
    at = _unsupported.get(symbol)
    return bool(at and time.time() - at < UNSUPPORTED_TTL)


class TwelveDataMarket:
    def __init__(self, api_key: Optional[str] = None, client: Optional[httpx.AsyncClient] = None):
        self.key = api_key or os.environ.get("TWELVE_DATA_API_KEY", "")
        self._client = client

    def _headers(self) -> dict:
        return {"Authorization": f"apikey {self.key}", "accept": "application/json"}

    async def _spend(self, credits: int) -> None:
        await BUCKET.acquire(wait_budget(float(os.environ.get("TWELVE_DATA_MAX_WAIT_S", "3") or 3)), cost=credits)

    def _check(self, body, http_status: int) -> dict:
        """Raise for an account-level error (any HTTP status: Twelve Data also reports errors in the body)."""
        if not isinstance(body, dict):
            raise TwelveDataError(http_status, "unexpected reply")
        if body.get("status") == "error" or http_status >= 400:
            code = int(body.get("code") or http_status or 500)
            msg = str(body.get("message") or "error")[:200]
            if code == 429:
                BUCKET.cool_down(60)
                raise RateLimited(f"twelvedata 429: {msg}")
            if code in (401, 403):
                BUCKET.cool_down(300)           # bad key or plan: stop hammering, fall back to CoinGecko meanwhile
            raise TwelveDataError(code, msg)
        return body

    async def _get(self, path: str, params: dict, credits: int = 1) -> dict:
        await self._spend(credits)
        c = self._client or shared_client()
        r = await c.get(f"{BASE}{path}", params=params, headers=self._headers(), timeout=15)
        try:
            body = r.json()
        except ValueError:
            body = None
        return self._check(body, r.status_code)

    async def prices(self, symbols: list[str]) -> dict[str, dict]:
        syms = [s.upper() for s in symbols if s and not _is_unsupported(s.upper())]
        if not syms:
            return {}
        if len(syms) == 1:
            s = syms[0]
            try:
                q = await self._get("/quote", {"symbol": pair(s)})
            except TwelveDataError as e:
                if e.code in (400, 404):
                    _unsupported[s] = time.time()
                    return {}
                raise
            row = _row(s, q)
            return {s: row} if row else {}
        await self._spend(len(syms))
        c = self._client or shared_client()
        r = await c.post(f"{BASE}/batch", json={s: {"url": f"/quote?symbol={pair(s)}"} for s in syms},
                         headers=self._headers(), timeout=20)
        try:
            body = r.json()
        except ValueError:
            body = None
        self._check(body, r.status_code)
        out: dict[str, dict] = {}
        for s, item in (body.get("data") or {}).items():
            resp = (item or {}).get("response") or {}
            if (item or {}).get("status") == "success" and resp.get("status") != "error":
                row = _row(s, resp)
                if row:
                    out[s] = row
                continue
            code = int(resp.get("code") or 0)
            if code in (400, 404):
                _unsupported[s] = time.time()
            elif code == 429:
                BUCKET.cool_down(60)
            elif code in (401, 403):
                BUCKET.cool_down(300)
        return out

    async def history(self, symbol: str, days: int) -> list[tuple[str, float]]:
        """Daily closes [(YYYY-MM-DD, usd)], oldest first."""
        s = symbol.upper()
        if _is_unsupported(s):
            raise TwelveDataError(404, f"{s} not on Twelve Data")
        try:
            body = await self._get("/time_series", {"symbol": pair(s), "interval": "1day", "timezone": "UTC",
                                                    "outputsize": max(1, min(int(days), MAX_OUTPUTSIZE)), "order": "asc"})
        except TwelveDataError as e:
            if e.code in (400, 404):
                _unsupported[s] = time.time()
            raise
        out: dict[str, float] = {}
        for v in body.get("values") or []:
            close = _num(v.get("close"))
            d = str(v.get("datetime") or "")[:10]
            if close and close > 0 and len(d) == 10:
                out[d] = close
        return sorted(out.items())
