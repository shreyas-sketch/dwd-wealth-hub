"""Binance adapter — spot + Dual Investment (developers.binance.com).

Signed endpoints: HMAC-SHA256 of the percent-encoded query string with the
secret, `signature` appended, `X-MBX-APIKEY` header (from 2026-01-15 the payload
must be percent-encoded BEFORE signing — urlencode does that).

  key permissions   GET  /sapi/v1/account/apiRestrictions
  balances          GET  /api/v3/account
  dual products     GET  /sapi/v1/dci/product/list      (optionType, exercisedCoin, investCoin)
  dual subscribe    POST /sapi/v1/dci/product/subscribe (id, orderId, depositAmount, autoCompoundPlan)
  dual positions    GET  /sapi/v1/dci/product/positions
  candles / price   GET  /api/v3/klines · /api/v3/ticker/price (public)
  orders            POST/GET/DELETE /api/v3/order

# NEEDS (confirm on a real Indian-KYC key, §13.6 day-1 probe): which DCI
# products are offered to Indian accounts, and the settled-position fields
# (settle price / converted flag) — mapped in _position() only.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

from .base import ExchangeError, KeyPermissions, Order, Position, Product

BASE = os.environ.get("BINANCE_API_BASE", "https://api.binance.com")


class BinanceClient:
    venue = "binance"

    def __init__(self, api_key: str, api_secret: str, client: Optional[httpx.AsyncClient] = None):
        self._key, self._secret, self._client = api_key, api_secret, client

    async def _req(self, method: str, path: str, params: Optional[dict] = None, signed: bool = True):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 10000
            q = urlencode(params)
            params["signature"] = hmac.new(self._secret.encode(), q.encode(), hashlib.sha256).hexdigest()
            headers["X-MBX-APIKEY"] = self._key
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            r = await client.request(method, BASE + path, params=params, headers=headers)
        except httpx.HTTPError as e:
            raise ExchangeError(f"binance {path}: {e}", retry=True)
        finally:
            if self._client is None:
                await client.aclose()
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            code = body.get("code") if isinstance(body, dict) else None
            raise ExchangeError(f"binance {path}: {code} {body.get('msg') if isinstance(body, dict) else body}",
                                code="auth" if code in (-2014, -2015, -1022) else "exchange_error",
                                retry=r.status_code >= 500 or r.status_code == 429)
        return body

    async def permissions(self) -> KeyPermissions:
        b = await self._req("GET", "/sapi/v1/account/apiRestrictions")
        return KeyPermissions(can_read=bool(b.get("enableReading")),
                              can_trade=bool(b.get("enableSpotAndMarginTrading")),
                              can_withdraw=bool(b.get("enableWithdrawals") or b.get("enableInternalTransfer")),
                              ip_restricted=bool(b.get("ipRestrict")), raw=b)

    async def balances(self) -> dict[str, float]:
        b = await self._req("GET", "/api/v3/account", {"omitZeroBalances": "true"})
        return {x["asset"]: float(x["free"]) for x in b.get("balances", []) if float(x["free"]) > 0}

    @staticmethod
    def _product(p: dict) -> Product:
        call = p.get("optionType") == "CALL"
        return Product(venue="binance", kind="dual", product_id=str(p["id"]), order_ref=str(p.get("orderId")),
                       invest_coin=p["investCoin"], exercised_coin=p["exercisedCoin"], option_type=p["optionType"],
                       underlying=p["investCoin"] if call else p["exercisedCoin"], strike=float(p["strikePrice"]),
                       apr=float(p["apr"]), tenor_days=int(p.get("duration") or 0), settle_at=int(p["settleDate"]),
                       min_amount=float(p.get("minAmount") or 0), max_amount=float(p.get("maxAmount") or 0),
                       can_purchase=bool(p.get("canPurchase", True)), raw=p)

    async def dual_products(self, underlying: str, option_type: str) -> list[Product]:
        call = option_type == "CALL"
        out, page = [], 1
        while page <= 5:
            b = await self._req("GET", "/sapi/v1/dci/product/list", {
                "optionType": option_type, "investCoin": underlying if call else "USDT",
                "exercisedCoin": "USDT" if call else underlying, "pageSize": 100, "pageIndex": page})
            rows = b.get("list") or []
            out += [self._product(p) for p in rows]
            if len(out) >= int(b.get("total") or 0) or not rows:
                break
            page += 1
        return out

    @staticmethod
    def _position(p: dict) -> Position:
        call = p.get("optionType") == "CALL"
        st = (p.get("purchaseStatus") or p.get("status") or "").upper()
        status = "settled" if st in ("SETTLED", "SETTLE") else "failed" if "FAIL" in st else "subscribed"
        settle_price = p.get("settlePrice") or p.get("settledPrice")           # NEEDS confirm field
        return Position(venue="binance", kind="dual", position_id=str(p.get("positionId") or p.get("id")),
                        product_id=str(p.get("orderId")), invest_coin=p["investCoin"],
                        exercised_coin=p["exercisedCoin"], option_type=p.get("optionType", ""),
                        underlying=p["investCoin"] if call else p["exercisedCoin"],
                        strike=float(p["strikePrice"]), apr=float(p["apr"]),
                        amount=float(p.get("subscriptionAmount") or 0), tenor_days=int(p.get("duration") or 0),
                        settle_at=int(p["settleDate"]), subscribed_at=int(p.get("purchaseTime") or 0),
                        status=status, settle_price=float(settle_price) if settle_price else None, raw=p)

    async def dual_subscribe(self, product: Product, amount: float) -> Position:
        b = await self._req("POST", "/sapi/v1/dci/product/subscribe", {
            "id": product.product_id, "orderId": product.order_ref, "depositAmount": f"{amount:.8f}".rstrip("0").rstrip("."),
            "autoCompoundPlan": "NONE"})
        if b.get("purchaseStatus") not in ("PURCHASE_SUCCESS", "PENDING", "PURCHASE_PENDING"):
            raise ExchangeError(f"binance subscribe: {b.get('purchaseStatus')}", code="not_available")
        return self._position(b)

    async def dual_positions(self) -> list[Position]:
        out, page = [], 1
        while page <= 10:
            b = await self._req("GET", "/sapi/v1/dci/product/positions", {"pageSize": 100, "pageIndex": page})
            rows = b.get("list") or []
            out += [self._position(p) for p in rows]
            if len(out) >= int(b.get("total") or 0) or not rows:
                break
            page += 1
        return out

    async def daily_closes(self, symbol: str, days: int) -> list[float]:
        b = await self._req("GET", "/api/v3/klines", {"symbol": symbol, "interval": "1d", "limit": min(days, 1000)},
                            signed=False)
        return [float(k[4]) for k in b]

    async def price_at(self, symbol: str, ts_ms: int) -> float:
        b = await self._req("GET", "/api/v3/klines", {"symbol": symbol, "interval": "1m", "startTime": ts_ms,
                                                       "limit": 1}, signed=False)
        if not b:
            raise ExchangeError("no candle at settlement time")
        return float(b[0][1])                      # open of the settlement minute

    async def symbol_filters(self, symbol: str) -> dict:
        """tick size, step size and min notional, so grid prices/quantities are valid."""
        b = await self._req("GET", "/api/v3/exchangeInfo", {"symbol": symbol}, signed=False)
        f = {x["filterType"]: x for x in b["symbols"][0]["filters"]}
        return {"tick": float(f["PRICE_FILTER"]["tickSize"]), "step": float(f["LOT_SIZE"]["stepSize"]),
                "min_notional": float((f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}).get("minNotional") or 5)}

    async def last_price(self, symbol: str) -> float:
        return float((await self._req("GET", "/api/v3/ticker/price", {"symbol": symbol}, signed=False))["price"])

    @staticmethod
    def _order(b: dict) -> Order:
        st = {"NEW": "open", "PARTIALLY_FILLED": "partial", "FILLED": "filled", "CANCELED": "cancelled",
              "EXPIRED": "cancelled", "REJECTED": "cancelled"}.get(b.get("status"), "open")
        qty, filled = float(b.get("origQty") or 0), float(b.get("executedQty") or 0)
        quote = float(b.get("cummulativeQuoteQty") or 0)
        return Order(venue="binance", order_id=str(b["orderId"]), symbol=b["symbol"], side=b["side"],
                     price=float(b["price"]) if float(b.get("price") or 0) else None, qty=qty, filled_qty=filled,
                     status=st, avg_price=quote / filled if filled else None, quote_qty=quote or None)

    async def limit_order(self, symbol, side, price, qty, client_id) -> Order:
        return self._order(await self._req("POST", "/api/v3/order", {
            "symbol": symbol, "side": side, "type": "LIMIT", "timeInForce": "GTC", "price": f"{price:.8f}",
            "quantity": f"{qty:.8f}", "newClientOrderId": client_id[:36], "newOrderRespType": "RESULT"}))

    async def market_buy_quote(self, symbol, quote_amount, client_id) -> Order:
        return self._order(await self._req("POST", "/api/v3/order", {
            "symbol": symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": f"{quote_amount:.2f}",
            "newClientOrderId": client_id[:36], "newOrderRespType": "RESULT"}))

    async def order(self, symbol, order_id) -> Order:
        return self._order(await self._req("GET", "/api/v3/order", {"symbol": symbol, "orderId": order_id}))

    async def cancel(self, symbol, order_id) -> None:
        await self._req("DELETE", "/api/v3/order", {"symbol": symbol, "orderId": order_id})
