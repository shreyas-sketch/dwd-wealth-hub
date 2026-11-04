"""One adapter interface, one file per venue (the §10 vendor pattern)."""
from .base import (ExchangeError, KeyPermissions, Order, PermissionRejected, Product, Position,  # noqa: F401
                   VENUES)


def _fake(venue: str) -> bool:
    """Venues are live whenever the layer is on (the keys are the user's). Fake only for
    tests/QA: EXCHANGE_<VENUE>_MODE=fake, or QA_MODE — never in production."""
    import os
    if (os.environ.get("APP_ENV") or "").lower() == "production":
        return False
    m = (os.environ.get(f"EXCHANGE_{venue.upper()}_MODE") or "").lower()
    return m == "fake" or (not m and (os.environ.get("QA_MODE") or "").lower() in ("1", "true", "yes"))


def adapter_for(venue: str, api_key: str, api_secret: str, passphrase: str | None = None):
    if _fake(venue):
        from .fake import FakeExchange
        return FakeExchange(venue, api_key)
    if venue == "binance":
        from .binance import BinanceClient
        return BinanceClient(api_key, api_secret)
    if venue == "kucoin":
        from .kucoin import KucoinClient
        return KucoinClient(api_key, api_secret, passphrase or "")
    raise ExchangeError(f"unknown venue {venue}")


def public_client(venue: str = "binance"):
    """Unauthenticated client for product lists and candles (nightly sync)."""
    if _fake(venue):
        from .fake import FakeExchange
        return FakeExchange(venue, "public")
    if venue == "binance":
        from .binance import BinanceClient
        import os
        # Binance's DCI product list is a signed endpoint: the nightly sync uses
        # Mudita's own READ-ONLY key. # NEEDS: BINANCE_READ_KEY / BINANCE_READ_SECRET
        return BinanceClient(os.environ.get("BINANCE_READ_KEY", ""), os.environ.get("BINANCE_READ_SECRET", ""))
    if venue == "kucoin":
        from .kucoin import KucoinClient
        import os
        return KucoinClient(os.environ.get("KUCOIN_READ_KEY", ""), os.environ.get("KUCOIN_READ_SECRET", ""),
                            os.environ.get("KUCOIN_READ_PASSPHRASE", ""))
    raise ExchangeError(f"unknown venue {venue}")
