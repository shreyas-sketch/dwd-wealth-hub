"""Feature switches with full control from Admin › Features (from Bullzeye core).

Every switch can be set in the admin panel; the admin setting wins over the server
environment variable, which stays as the default. Settings live in Mongo
(`feature_flags`) and are cached in-process; the process refreshes the cache
every 30 s, so a toggle
takes effect within about a minute everywhere — no redeploy.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

_ON = ("1", "true", "yes", "on")
log = logging.getLogger("core.flags")
_cache: dict = {"at": 0.0, "values": {}}
REFRESH_SECONDS = 30

# key → (label, group, description, default when neither admin nor env sets it, env aliases)
FLAGS: dict[str, tuple] = {
    "WHATSAPP_OTP": ("WhatsApp OTP", "Login", "Send login codes on WhatsApp (AiSensy). Off: SMS only.", False, ("OTP_WHATSAPP_ENABLED",)),
    "CRYPTO_COMMITTEE": ("Daily AI verdicts (top 10)", "Crypto Verdicts", "Daily bull/bear verdicts on the top 10 coins at 05:30 IST (Anthropic cost).", True, ()),
    "MONDAY_PICKS": ("Monday Crypto Picks", "Crypto Verdicts", "Show the published Monday picks inside Crypto Verdicts.", True, ()),
    "AUTOPILOT": ("SIP Autopilot", "Autopilot", "Exchange linking and scheduled buys on KuCoin/Binance.", True, ("CRYPTO_DCA",)),
    "VENUE_BINANCE_ENABLED": ("Binance", "Autopilot", "Allow Binance for Autopilot and Baskets.", True, ()),
    "VENUE_KUCOIN_ENABLED": ("KuCoin", "Autopilot", "Allow KuCoin for Autopilot and Baskets.", True, ()),
    "BASKET_INVEST": ("Basket real-money buys", "Baskets", "Let ₹5,000 members buy a basket on their own exchange (practice always works).", True, ()),
    "RADAR": ("Early Coin Radar", "₹5,000 features", "Hourly scan of new listings and trending coins.", True, ()),
    "NEWS": ("News Decoder", "₹5,000 features", "News fetch and AI summaries every 2 hours.", True, ()),
    "P2P": ("P2P Rate Finder", "₹5,000 features", "Live USDT/INR P2P rates.", True, ()),
    "ASK": ("Ask Deepak AI", "₹5,000 features", "AI answers from the knowledge base.", True, ()),
    "CRASH_COACH": ("Crash Coach alerts", "₹5,000 features", "Alert when BTC falls past a crash level from its 30-day high.", True, ()),
    "WHATSAPP_ALERTS": ("Alerts on WhatsApp", "Alerts", "Also send inbox alerts on WhatsApp (needs AiSensy templates).", False, ()),
}


def _env(key: str) -> Optional[bool]:
    for n in (key, *FLAGS.get(key, (None,) * 5)[4]):
        v = os.environ.get(n)
        if v is not None and v.strip() != "":
            return v.strip().lower() in _ON
    return None


def is_on(key: str) -> bool:
    """Admin setting → environment variable → built-in default."""
    v = _cache["values"].get(key)
    if v is not None:
        return bool(v)
    e = _env(key)
    if e is not None:
        return e
    return bool(FLAGS.get(key, (None, None, None, False))[3])


async def refresh(db, force: bool = False) -> None:
    if not force and time.time() - _cache["at"] < REFRESH_SECONDS:
        return
    try:
        _cache["values"] = {d["_id"]: bool(d["on"]) async for d in db.feature_flags.find({"on": {"$exists": True}})
                            if d["_id"] in FLAGS}
        _cache["at"] = time.time()
    except Exception:  # noqa: BLE001 — a DB blip keeps the last known values
        log.warning("feature flags refresh failed", exc_info=True)


async def set_flag(db, key: str, on: Optional[bool], by: str) -> None:
    if key not in FLAGS:
        raise KeyError(key)
    if on is None:                       # back to the environment/default
        await db.feature_flags.delete_one({"_id": key})
    else:
        from growth.clock import utcnow
        await db.feature_flags.replace_one({"_id": key}, {"_id": key, "on": bool(on), "by": by, "at": utcnow()}, upsert=True)
    await refresh(db, force=True)


def listing() -> list[dict]:
    out = []
    for k, (label, group, desc, default, _) in FLAGS.items():
        admin = _cache["values"].get(k)
        env = _env(k)
        out.append({"key": k, "label": label, "group": group, "description": desc, "on": is_on(k),
                    "source": "admin" if admin is not None else "environment" if env is not None else "default"})
    return out
