"""Deterministic in-memory exchange for tests and QA (EXCHANGE_*_MODE=fake / QA_MODE).

State is class-level (shared by every instance of the same venue) so a test can
move prices (`FakeExchange.set_price`) and settle positions (`settle_all`).
Key permission scenario is picked by the api_key text: contains 'withdraw' → withdrawals
on, 'readonly…' → cannot trade; anything else is a good trade-only key.
"""
from __future__ import annotations

import math
import secrets
import time
from typing import Optional

from .base import ExchangeError, KeyPermissions, Order, Position, Product

START = {"BTC": 64000.0, "ETH": 3100.0, "BNB": 590.0, "SOL": 150.0}


class FakeExchange:
    prices: dict[str, float] = {}
    positions: dict[str, dict[str, Position]] = {}
    orders: dict[str, dict[str, Order]] = {}
    balances_: dict[str, dict[str, float]] = {}

    def __init__(self, venue: str, api_key: str):
        self.venue, self.key = venue, api_key

    # ---- test helpers
    @classmethod
    def reset(cls):
        cls.prices, cls.positions, cls.orders, cls.balances_ = {}, {}, {}, {}

    @classmethod
    def set_price(cls, coin: str, price: float):
        cls.prices[coin] = price
        for book in cls.orders.values():
            for o in book.values():
                if o.status == "open" and o.symbol == f"{coin}USDT":
                    if (o.side == "BUY" and price <= o.price) or (o.side == "SELL" and price >= o.price):
                        o.status, o.filled_qty, o.avg_price = "filled", o.qty, o.price
                        o.quote_qty = o.qty * o.price

    @classmethod
    def settle_all(cls, now_ms: Optional[int] = None):
        now_ms = now_ms or int(time.time() * 1000)
        for book in cls.positions.values():
            for p in book.values():
                if p.status == "subscribed" and p.settle_at <= now_ms:
                    px = cls.price(p.underlying)
                    p.status, p.settle_price = "settled", px
                    p.converted = px >= p.strike if p.option_type == "CALL" else px <= p.strike
                    interest = p.amount * p.apr * p.tenor_days / 365
                    if p.converted:
                        p.payout_coin = p.exercised_coin
                        p.payout_amount = (p.amount + interest) * p.strike if p.option_type == "CALL" \
                            else (p.amount + interest) / p.strike
                    else:
                        p.payout_coin, p.payout_amount = p.invest_coin, p.amount + interest

    @classmethod
    def price(cls, coin: str) -> float:
        if coin in cls.prices:
            return cls.prices[coin]
        try:                                   # follow the fake market so screens agree
            from market.fake import FakeMarket
            c = FakeMarket()._coin(coin)
            if c and c.get("price_usd"):
                return float(c["price_usd"])
        except Exception:  # noqa: BLE001
            pass
        return START.get(coin, 10.0)

    # ---- interface
    async def permissions(self) -> KeyPermissions:
        k = self.key.lower()
        return KeyPermissions(can_read=True, can_trade=not k.startswith("readonly"),
                              can_withdraw="withdraw" in k, ip_restricted=k.endswith("ip"),
                              earn=True, raw={"fake": True})

    async def balances(self) -> dict[str, float]:
        return self.balances_.setdefault(self.key, {"USDT": 5000.0, "BTC": 0.05, "ETH": 1.0})

    async def dual_products(self, underlying: str, option_type: str) -> list[Product]:
        from .kucoin import earn_api_on
        if self.venue == "kucoin" and not earn_api_on():
            return []                      # same as the live adapter while KUCOIN_EARN_API is off
        spot = self.price(underlying)
        out = []
        now = int(time.time() * 1000)
        for tenor in (1, 3, 7):
            for i, step in enumerate((0.02, 0.04, 0.06, 0.09)):
                strike = round(spot * (1 + step) if option_type == "CALL" else spot * (1 - step), 2)
                apr = round(0.9 * math.exp(-step * 25) * (1.2 if tenor == 1 else 1.0) + 0.03, 4)
                pid = f"{self.venue}-{underlying}-{option_type}-{tenor}-{i}"
                out.append(Product(
                    venue=self.venue, kind="dual", product_id=pid, order_ref=pid + "-o",
                    invest_coin=underlying if option_type == "CALL" else "USDT",
                    exercised_coin="USDT" if option_type == "CALL" else underlying, option_type=option_type,
                    underlying=underlying, strike=strike, apr=apr, tenor_days=tenor,
                    settle_at=now + tenor * 86400_000, min_amount=0.0001 if option_type == "CALL" else 10,
                    max_amount=1e6, can_purchase=True))
        return out

    async def dual_subscribe(self, product: Product, amount: float) -> Position:
        if amount < product.min_amount:
            raise ExchangeError("below minimum", code="not_available")
        p = Position(venue=self.venue, kind=product.kind, position_id="pos_" + secrets.token_hex(5),
                     product_id=product.product_id, invest_coin=product.invest_coin,
                     exercised_coin=product.exercised_coin, option_type=product.option_type,
                     underlying=product.underlying, strike=product.strike, apr=product.apr, amount=amount,
                     tenor_days=product.tenor_days, settle_at=product.settle_at,
                     subscribed_at=int(time.time() * 1000), status="subscribed")
        self.positions.setdefault(self.key, {})[p.position_id] = p
        return p

    async def dual_positions(self) -> list[Position]:
        return list(self.positions.get(self.key, {}).values())

    async def daily_closes(self, symbol: str, days: int) -> list[float]:
        coin = symbol.replace("USDT", "")
        base = self.price(coin)
        seed = sum(map(ord, coin))
        return [base * (1 + 0.03 * math.sin((i + seed) / 3.0) + 0.01 * math.cos(i * 1.7)) for i in range(days)]

    async def price_at(self, symbol: str, ts_ms: int) -> float:
        return self.price(symbol.replace("USDT", ""))

    async def last_price(self, symbol: str) -> float:
        return self.price(symbol.replace("USDT", ""))

    async def symbol_filters(self, symbol: str) -> dict:
        return {"tick": 0.01, "step": 0.00001, "min_notional": 5.0}

    async def limit_order(self, symbol, side, price, qty, client_id) -> Order:
        o = Order(venue=self.venue, order_id="ord_" + secrets.token_hex(5), symbol=symbol, side=side, price=price,
                  qty=qty, filled_qty=0.0, status="open")
        self.orders.setdefault(self.key, {})[o.order_id] = o
        return o

    async def market_buy_quote(self, symbol, quote_amount, client_id) -> Order:
        px = await self.last_price(symbol)
        bal = await self.balances()
        if bal.get("USDT", 0.0) + 1e-9 < quote_amount:
            raise ExchangeError("Insufficient USDT balance", code="insufficient_balance")
        bal["USDT"] = bal.get("USDT", 0.0) - quote_amount
        coin = symbol.replace("USDT", "")
        bal[coin] = bal.get(coin, 0.0) + quote_amount / px
        o = Order(venue=self.venue, order_id="ord_" + secrets.token_hex(5), symbol=symbol, side="BUY", price=None,
                  qty=quote_amount / px, filled_qty=quote_amount / px, status="filled", avg_price=px,
                  quote_qty=quote_amount)
        self.orders.setdefault(self.key, {})[o.order_id] = o
        return o

    async def order(self, symbol, order_id) -> Order:
        o = self.orders.get(self.key, {}).get(order_id)
        if not o:
            raise ExchangeError("unknown order")
        return o

    async def cancel(self, symbol, order_id) -> None:
        o = self.orders.get(self.key, {}).get(order_id)
        if o and o.status == "open":
            o.status = "cancelled"
