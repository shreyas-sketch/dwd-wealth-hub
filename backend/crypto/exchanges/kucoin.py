"""KuCoin adapter — spot + Structured Earn (Dual / Shark Fin) behind a flag.

Auth (API key version 2): headers KC-API-KEY, KC-API-TIMESTAMP (ms),
KC-API-SIGN = base64(HMAC-SHA256(secret, timestamp + METHOD + path?query + body)),
KC-API-PASSPHRASE = base64(HMAC-SHA256(secret, passphrase)), KC-API-KEY-VERSION: 2.

  key permissions   GET  /api/v1/user/api-key            (permission "General,Spot,Earn"…, ipWhitelist)
  balances          GET  /api/v1/accounts?type=trade
  structured orders GET  /api/v1/struct-earn/orders?categories=DUAL_CLASSIC,…   (documented)
  dual products     GET  /api/v1/struct-earn/dual/products          # NEEDS confirm path
  purchase          POST /api/v1/struct-earn/orders                 # NEEDS confirm path + body
  candles / price   GET  /api/v1/market/candles · /api/v1/market/orderbook/level1 (public)
  orders            POST /api/v1/hf/orders · GET/DELETE /api/v1/hf/orders/{id}?symbol=

The structured-earn endpoints are documented but reported unstable (may return
400100). KUCOIN_EARN_API=true turns them on after the week-1 D1 test (§13.6);
until then Dual/Shark Fin on KuCoin is the UI-guided flow with read-only
tracking of the user's structured orders.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

from .base import ExchangeError, KeyPermissions, Order, Position, Product

BASE = os.environ.get("KUCOIN_API_BASE", "https://api.kucoin.com")
GUIDED_URL = "https://www.kucoin.com/earn/structured-products"


def earn_api_on() -> bool:
    from crypto import kucoin_structured
    return kucoin_structured()


def pair(symbol: str) -> str:
    """BTCUSDT → BTC-USDT."""
    return symbol if "-" in symbol else f"{symbol[:-4]}-{symbol[-4:]}" if symbol.endswith("USDT") else symbol


class KucoinClient:
    venue = "kucoin"

    def __init__(self, api_key: str, api_secret: str, passphrase: str, client: Optional[httpx.AsyncClient] = None):
        self._key, self._secret, self._pass, self._client = api_key, api_secret, passphrase, client

    def _sign(self, s: str) -> str:
        return base64.b64encode(hmac.new(self._secret.encode(), s.encode(), hashlib.sha256).digest()).decode()

    async def _req(self, method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None,
                   signed: bool = True):
        q = f"?{urlencode(params)}" if params else ""
        data = json.dumps(body) if body else ""
        headers = {"Content-Type": "application/json"}
        if signed:
            ts = str(int(time.time() * 1000))
            headers.update({"KC-API-KEY": self._key, "KC-API-TIMESTAMP": ts,
                            "KC-API-SIGN": self._sign(ts + method + path + q + data),
                            "KC-API-PASSPHRASE": self._sign(self._pass), "KC-API-KEY-VERSION": "2"})
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            r = await client.request(method, BASE + path + q, content=data or None, headers=headers)
        except httpx.HTTPError as e:
            raise ExchangeError(f"kucoin {path}: {e}", retry=True)
        finally:
            if self._client is None:
                await client.aclose()
        b = r.json() if r.content else {}
        if r.status_code >= 400 or str(b.get("code")) != "200000":
            code = str(b.get("code"))
            raise ExchangeError(f"kucoin {path}: {code} {b.get('msg')}",
                                code="not_available" if code == "400100" else "auth" if code.startswith("4001")
                                else "exchange_error", retry=r.status_code >= 500 or r.status_code == 429)
        return b.get("data")

    async def permissions(self) -> KeyPermissions:
        d = await self._req("GET", "/api/v1/user/api-key")
        perms = {x.strip().lower() for x in (d.get("permission") or "").split(",")}
        return KeyPermissions(can_read="general" in perms, can_trade="spot" in perms,
                              can_withdraw="withdrawal" in perms or "transfer" in perms,
                              ip_restricted=bool(d.get("ipWhitelist")), earn="earn" in perms, raw=d)

    async def balances(self) -> dict[str, float]:
        d = await self._req("GET", "/api/v1/accounts", {"type": "trade"})
        return {a["currency"]: float(a["available"]) for a in d or [] if float(a["available"]) > 0}

    @staticmethod
    def _product(p: dict, kind: str) -> Product:
        call = (p.get("side") or p.get("optionType") or "").upper() in ("CALL", "SELL_HIGH", "SELL")
        inv, ex = p.get("investCurrency") or "", p.get("targetCurrency") or p.get("exercisedCurrency") or ""
        return Product(venue="kucoin", kind=kind, product_id=str(p.get("productId") or p.get("id")),
                       order_ref=str(p.get("productId") or p.get("id")), invest_coin=inv, exercised_coin=ex,
                       option_type="CALL" if call else "PUT", underlying=inv if call else ex,
                       strike=float(p.get("strikePrice") or 0), apr=float(p.get("apr") or p.get("returnRate") or 0),
                       tenor_days=int(p.get("duration") or p.get("period") or 0),
                       settle_at=int(p.get("settleTime") or p.get("expirationTime") or 0),
                       min_amount=float(p.get("minInvestAmount") or 0), max_amount=float(p.get("maxInvestAmount") or 0),
                       can_purchase=bool(p.get("purchasable", True)), raw=p)

    async def dual_products(self, underlying: str, option_type: str) -> list[Product]:
        if not earn_api_on():
            return []
        d = await self._req("GET", "/api/v1/struct-earn/dual/products",          # NEEDS confirm
                            {"category": "DUAL_CLASSIC", "strikeCurrency": underlying,
                             "investCurrency": underlying if option_type == "CALL" else "USDT"})
        return [self._product(p, "dual") for p in (d or [])]

    async def dual_subscribe(self, product: Product, amount: float) -> Position:
        if not earn_api_on():
            raise ExchangeError("KuCoin Earn API is not switched on", code="guided")
        d = await self._req("POST", "/api/v1/struct-earn/orders",                 # NEEDS confirm
                            body={"productId": product.product_id, "investAmount": str(amount),
                                  "investCurrency": product.invest_coin})
        return Position(venue="kucoin", kind=product.kind, position_id=str(d.get("orderId")),
                        product_id=product.product_id, invest_coin=product.invest_coin,
                        exercised_coin=product.exercised_coin, option_type=product.option_type,
                        underlying=product.underlying, strike=product.strike, apr=product.apr, amount=amount,
                        tenor_days=product.tenor_days, settle_at=product.settle_at,
                        subscribed_at=int(time.time() * 1000), status="subscribed", raw=d or {})

    async def dual_positions(self) -> list[Position]:
        """Documented read endpoint — used for tracking even in the guided flow."""
        d = await self._req("GET", "/api/v1/struct-earn/orders",
                            {"categories": "DUAL_CLASSIC,DUAL_BOOSTER,DUAL_EXTRA,SHARK_FIN", "pageSize": 100})
        out = []
        for o in (d or {}).get("items", []) if isinstance(d, dict) else d or []:
            st = (o.get("status") or "").upper()
            kind = "sharkfin" if "SHARK" in (o.get("category") or "").upper() else "dual"
            call = (o.get("side") or "").upper() in ("CALL", "SELL_HIGH", "SELL")
            out.append(Position(
                venue="kucoin", kind=kind, position_id=str(o.get("orderId")), product_id=str(o.get("productId")),
                invest_coin=o.get("investCurrency", ""), exercised_coin=o.get("targetCurrency", ""),
                option_type="CALL" if call else "PUT", underlying=o.get("strikeCurrency") or o.get("investCurrency", ""),
                strike=float(o.get("strikePrice") or 0), apr=float(o.get("apr") or 0),
                amount=float(o.get("investAmount") or 0), tenor_days=int(o.get("duration") or 0),
                settle_at=int(o.get("settleTime") or 0), subscribed_at=int(o.get("createdTime") or 0),
                status="settled" if st in ("SETTLED", "COMPLETED") else "subscribed",
                settle_price=float(o["settlePrice"]) if o.get("settlePrice") else None,
                payout_coin=o.get("settleCurrency"), payout_amount=float(o["settleAmount"]) if o.get("settleAmount") else None,
                raw=o))
        return out

    async def daily_closes(self, symbol: str, days: int) -> list[float]:
        end = int(time.time())
        d = await self._req("GET", "/api/v1/market/candles", {"type": "1day", "symbol": pair(symbol),
                                                               "startAt": end - days * 86400, "endAt": end}, signed=False)
        return [float(k[2]) for k in reversed(d or [])]           # newest first → oldest first; [2] = close

    async def price_at(self, symbol: str, ts_ms: int) -> float:
        d = await self._req("GET", "/api/v1/market/candles", {"type": "1min", "symbol": pair(symbol),
                                                               "startAt": ts_ms // 1000, "endAt": ts_ms // 1000 + 60},
                            signed=False)
        if not d:
            raise ExchangeError("no candle at settlement time")
        return float(d[-1][1])                     # open of the settlement minute

    async def last_price(self, symbol: str) -> float:
        return float((await self._req("GET", "/api/v1/market/orderbook/level1", {"symbol": pair(symbol)},
                                      signed=False))["price"])

    async def symbol_filters(self, symbol: str) -> dict:
        d = await self._req("GET", f"/api/v2/symbols/{pair(symbol)}", signed=False)
        return {"tick": float(d["priceIncrement"]), "step": float(d["baseIncrement"]),
                "min_notional": float(d.get("minFunds") or 1)}

    @staticmethod
    def _order(d: dict, symbol: str) -> Order:
        qty, filled = float(d.get("size") or 0), float(d.get("dealSize") or 0)
        active = d.get("active", True)
        status = "filled" if filled and filled >= qty else "cancelled" if not active and filled < qty and \
            d.get("cancelExist") else "partial" if filled else "open" if active else "filled"
        funds = float(d.get("dealFunds") or 0)
        return Order(venue="kucoin", order_id=str(d.get("id") or d.get("orderId")), symbol=symbol,
                     side=(d.get("side") or "").upper(), price=float(d["price"]) if d.get("price") else None,
                     qty=qty, filled_qty=filled, status=status, avg_price=funds / filled if filled else None,
                     quote_qty=funds or None)

    async def limit_order(self, symbol, side, price, qty, client_id) -> Order:
        d = await self._req("POST", "/api/v1/hf/orders", body={
            "clientOid": client_id[:40], "symbol": pair(symbol), "side": side.lower(), "type": "limit",
            "price": f"{price:.8f}", "size": f"{qty:.8f}"})
        return Order(venue="kucoin", order_id=str(d["orderId"]), symbol=symbol, side=side, price=price, qty=qty,
                     filled_qty=0, status="open")

    async def market_buy_quote(self, symbol, quote_amount, client_id) -> Order:
        d = await self._req("POST", "/api/v1/hf/orders", body={
            "clientOid": client_id[:40], "symbol": pair(symbol), "side": "buy", "type": "market",
            "funds": f"{quote_amount:.2f}"})
        return await self.order(symbol, d["orderId"])

    async def order(self, symbol, order_id) -> Order:
        return self._order(await self._req("GET", f"/api/v1/hf/orders/{order_id}", {"symbol": pair(symbol)}), symbol)

    async def cancel(self, symbol, order_id) -> None:
        await self._req("DELETE", f"/api/v1/hf/orders/{order_id}", {"symbol": pair(symbol)})
