"""The venue-neutral shapes every adapter returns."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

VENUES = ("binance", "kucoin")


class ExchangeError(Exception):
    def __init__(self, msg: str, *, code: str = "exchange_error", retry: bool = False):
        super().__init__(msg)
        self.code, self.retry = code, retry


class PermissionRejected(ExchangeError):
    def __init__(self, msg: str):
        super().__init__(msg, code="key_rejected")


@dataclass
class KeyPermissions:
    can_read: bool
    can_trade: bool
    can_withdraw: bool
    ip_restricted: bool
    earn: Optional[bool] = None          # KuCoin reports an Earn scope; Binance doesn't
    raw: dict = field(default_factory=dict)

    def problems(self) -> list[str]:
        out = []
        if self.can_withdraw:
            out.append("Withdrawals are switched on for this key. Create a key with withdrawals OFF.")
        if not self.can_read:
            out.append("This key can't read your account.")
        if not self.can_trade:
            out.append("This key can't trade. Switch on spot trading.")
        return out


@dataclass
class Product:
    """A subscribable structured product (dual investment / shark fin)."""
    venue: str
    kind: str                  # dual | sharkfin
    product_id: str
    order_ref: str             # Binance needs id + orderId to subscribe
    invest_coin: str
    exercised_coin: str
    option_type: str           # CALL = "sell high" (invest the coin) · PUT = "buy low" (invest USDT)
    underlying: str            # BTC, ETH …
    strike: float
    apr: float                 # 0.18 = 18% a year, as the exchange quotes it
    tenor_days: int
    settle_at: int             # epoch ms
    min_amount: float
    max_amount: float
    can_purchase: bool
    raw: dict = field(default_factory=dict)


@dataclass
class Position:
    venue: str
    kind: str
    position_id: str
    product_id: str
    invest_coin: str
    exercised_coin: str
    option_type: str
    underlying: str
    strike: float
    apr: float
    amount: float              # in invest_coin
    tenor_days: int
    settle_at: int
    subscribed_at: int
    status: str                # subscribed | settled | redeemed | failed
    settle_price: Optional[float] = None
    converted: Optional[bool] = None
    payout_coin: Optional[str] = None
    payout_amount: Optional[float] = None
    raw: dict = field(default_factory=dict)


@dataclass
class Order:
    venue: str
    order_id: str
    symbol: str                # BTCUSDT
    side: str                  # BUY | SELL
    price: Optional[float]
    qty: float
    filled_qty: float
    status: str                # open | filled | cancelled | partial
    avg_price: Optional[float] = None
    quote_qty: Optional[float] = None


class Exchange(Protocol):
    venue: str

    async def permissions(self) -> KeyPermissions: ...
    async def balances(self) -> dict[str, float]: ...
    async def dual_products(self, underlying: str, option_type: str) -> list[Product]: ...
    async def dual_subscribe(self, product: Product, amount: float) -> Position: ...
    async def dual_positions(self) -> list[Position]: ...
    async def daily_closes(self, symbol: str, days: int) -> list[float]: ...
    async def last_price(self, symbol: str) -> float: ...
    async def price_at(self, symbol: str, ts_ms: int) -> float: ...
    async def symbol_filters(self, symbol: str) -> dict: ...
    async def limit_order(self, symbol: str, side: str, price: float, qty: float, client_id: str) -> Order: ...
    async def market_buy_quote(self, symbol: str, quote_amount: float, client_id: str) -> Order: ...
    async def order(self, symbol: str, order_id: str) -> Order: ...
    async def cancel(self, symbol: str, order_id: str) -> None: ...
