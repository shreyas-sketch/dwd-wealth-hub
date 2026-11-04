"""Indian mobile number normalisation. Everything is stored as E.164 (+91XXXXXXXXXX)."""
from __future__ import annotations

import re

_DIGITS = re.compile(r"\D+")


class InvalidPhone(ValueError):
    pass


def normalise_in_mobile(raw: str) -> str:
    """Accepts 9876543210, 09876543210, 919876543210, +91 98765-43210.
    Rejects anything that is not a 10-digit Indian mobile starting 6–9."""
    digits = _DIGITS.sub("", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise InvalidPhone("Enter a 10-digit Indian mobile number.")
    if len(set(digits)) == 1:
        raise InvalidPhone("Enter a valid mobile number.")
    return "+91" + digits


def mask(e164: str) -> str:
    """+919876543210 → +91 98•••••210"""
    d = e164[3:]
    return f"+91 {d[:2]}•••••{d[-3:]}"
