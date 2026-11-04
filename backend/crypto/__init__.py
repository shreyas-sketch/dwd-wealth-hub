"""Exchange rails (from Bullzeye): the user's OWN KuCoin/Binance account, trade-only API key.

Flags (Admin › Features): AUTOPILOT (master), VENUE_BINANCE_ENABLED, VENUE_KUCOIN_ENABLED.
Keys that can withdraw are refused; keys are envelope-encrypted (vault.py) and never returned.
"""
from core.flags import is_on


def rails_enabled() -> bool:
    return is_on("AUTOPILOT")


def venue_enabled(venue: str) -> bool:
    return rails_enabled() and is_on(f"VENUE_{venue.upper()}_ENABLED")


def enabled_venues() -> tuple[str, ...]:
    return tuple(v for v in ("binance", "kucoin") if venue_enabled(v))


VENUE_NAMES = {"kucoin": "KuCoin", "binance": "Binance"}


def venue_name(venue: str) -> str:
    return VENUE_NAMES.get(venue, str(venue).title())


def kucoin_structured() -> bool:
    """Structured earn is not part of this app (kept so the copied KuCoin adapter imports)."""
    return False
