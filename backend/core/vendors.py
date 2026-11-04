"""One switch for every outside vendor that is not connected yet.

Each vendor client has a live implementation (written against the vendor's
public docs) and a fake one (deterministic, no network) used by the tests and
by local QA. `vendor_mode("razorpay")` decides which one the app builds:

    <NAME>_MODE=live   use the real client (keys must be set)
    <NAME>_MODE=fake   use the fake (refused when APP_ENV=production)
    <NAME>_MODE=off    feature shows "coming soon"; nothing is called
    (unset)            live if the vendor's required keys are present, else off

QA_MODE=true makes every unset vendor fake, so the whole app runs locally.
"""
from __future__ import annotations

import os

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "razorpay": ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"),
    "aisensy": ("AISENSY_API_KEY",),
    "msg91": ("MSG91_AUTH_KEY", "MSG91_OTP_TEMPLATE_ID"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "kronos": ("KRONOS_API_URL", "KRONOS_API_KEY"),
    # Public data sources need no key; they are live unless set to fake/off.
    "market": (),
    "goplus": (),
    "news": (),
    "p2p": (),
    "unlocks": ("TOKEN_UNLOCKS_API_KEY",),
}

KEYLESS = {"market", "goplus", "news", "p2p"}


class VendorModeError(RuntimeError):
    pass


def vendor_mode(name: str) -> str:
    explicit = (os.environ.get(f"{name.upper()}_MODE") or "").strip().lower()
    prod = (os.environ.get("APP_ENV") or "").lower() == "production"
    if explicit:
        if explicit not in ("live", "fake", "off"):
            raise VendorModeError(f"{name.upper()}_MODE must be live|fake|off")
        if explicit == "fake" and prod:
            raise VendorModeError(f"{name.upper()}_MODE=fake is not allowed in production")
        return explicit
    if (os.environ.get("QA_MODE") or "").lower() in ("1", "true", "yes") and not prod:
        return "fake"
    if name in KEYLESS:
        return "live"
    keys = REQUIRED_KEYS.get(name, ())
    return "live" if keys and all(os.environ.get(k) for k in keys) else "off"


def status() -> dict[str, str]:
    out = {}
    for n in REQUIRED_KEYS:
        try:
            out[n] = vendor_mode(n)
        except VendorModeError as e:
            out[n] = f"error: {e}"
    return out
