"""Admin-editable app settings (one Mongo document, cached briefly).

    settings {_id: "app", trial_days, scenario_rates: {bad, average, good}, crash_levels, anon_xray_per_day}

Validation is declared once in SPEC (the admin form reads the same limits from GET /admin/settings/spec).
An out-of-range value is rejected with a 400 that names the field, never silently clipped: QA (3 Nov) found
31 trial days quietly saved as 30 and a crash level of 3 quietly dropped.
"""
from __future__ import annotations

import math
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional

DEFAULTS: dict = {
    "trial_days": 3,                                   # new accounts get the ₹5,000 plan as a trial (webinar → Day 3 call)
    "scenario_rates": {"bad": 0.0, "average": 15.0, "good": 35.0},   # % a year — labelled assumptions in My Crypto Plan
    "crash_levels": [20, 30, 40],                      # BTC fall from its 30-day high, in %
    "anon_xray_per_day": 1,                            # Coin X-Ray checks per day without an account
}


@dataclass(frozen=True)
class NumberRule:
    label: str
    lo: float
    hi: float
    integer: bool = True
    unit: str = ""

    def as_dict(self) -> dict:
        return {"label": self.label, "min": self.lo, "max": self.hi, "integer": self.integer, "unit": self.unit}


SPEC: dict[str, NumberRule] = {
    "trial_days": NumberRule("Trial days", 0, 30, unit="days"),
    "anon_xray_per_day": NumberRule("X-Ray checks a day without login", 0, 20),
    "scenario_rates.bad": NumberRule("Bad-case rate", -50, 100, integer=False, unit="%"),
    "scenario_rates.average": NumberRule("Average-case rate", -50, 100, integer=False, unit="%"),
    "scenario_rates.good": NumberRule("Good-case rate", -50, 100, integer=False, unit="%"),
    "crash_levels": NumberRule("Crash level", 5, 90, unit="%"),
}
MAX_CRASH_LEVELS = 6

_cache: dict = {"at": 0.0, "value": None}
TTL = 20


async def get(db) -> dict:
    if _cache["value"] is not None and time.time() - _cache["at"] < TTL:
        return deepcopy(_cache["value"])
    doc = await db.settings.find_one({"_id": "app"}) or {}
    out = deepcopy(DEFAULTS)
    for k in DEFAULTS:
        if k in doc and doc[k] is not None:
            out[k] = doc[k]
    _cache.update(at=time.time(), value=out)
    return deepcopy(out)


def spec() -> dict:
    return {"fields": {k: r.as_dict() for k, r in SPEC.items()}, "max_crash_levels": MAX_CRASH_LEVELS}


class SettingsError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(errors.values()))
        self.errors = errors


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def _number(field: str, raw: Any, errors: dict[str, str], *, label: Optional[str] = None) -> Optional[float]:
    """Parse one value against SPEC[field]; record a plain sentence in `errors` and return None when it's wrong."""
    rule = SPEC[field]
    name = label or rule.label
    if isinstance(raw, bool) or raw is None or (isinstance(raw, str) and not raw.strip()):
        errors[field] = f"{name} is required."
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        errors[field] = f"{name} must be a number."
        return None
    if not math.isfinite(v):
        errors[field] = f"{name} must be a number."
        return None
    if rule.integer and not v.is_integer():
        errors[field] = f"{name} must be a whole number."
        return None
    if v < rule.lo or v > rule.hi:
        unit = f" {rule.unit}" if rule.unit and rule.unit != "%" else rule.unit
        errors[field] = f"{name} must be between {_fmt(rule.lo)}{unit} and {_fmt(rule.hi)}{unit} (you entered {_fmt(v)})."
        return None
    return int(v) if rule.integer else v


def validate(patch: Any) -> dict:
    """Return the cleaned partial update, or raise SettingsError with every problem (field → sentence)."""
    if not isinstance(patch, dict):
        raise SettingsError({"settings": "Settings must be sent as an object."})
    errors: dict[str, str] = {}
    clean: dict = {}
    for key in ("trial_days", "anon_xray_per_day"):
        if key in patch and patch[key] is not None:
            v = _number(key, patch[key], errors)
            if v is not None:
                clean[key] = v
    if "scenario_rates" in patch and patch["scenario_rates"] is not None:
        r = patch["scenario_rates"]
        if not isinstance(r, dict):
            errors["scenario_rates"] = "Scenario rates must have bad, average and good."
        else:
            rates = {}
            for k in ("bad", "average", "good"):
                v = _number(f"scenario_rates.{k}", r.get(k, DEFAULTS["scenario_rates"][k]), errors)
                if v is not None:
                    rates[k] = float(v)
            if len(rates) == 3:
                if not rates["bad"] <= rates["average"] <= rates["good"]:
                    errors["scenario_rates"] = "Rates must go up from bad to average to good."
                else:
                    clean["scenario_rates"] = rates
    if "crash_levels" in patch and patch["crash_levels"] is not None:
        raw = patch["crash_levels"]
        if not isinstance(raw, list) or not raw:
            errors["crash_levels"] = "Add at least one crash level, e.g. 20, 30, 40."
        elif len(raw) > MAX_CRASH_LEVELS:
            errors["crash_levels"] = f"Use at most {MAX_CRASH_LEVELS} crash levels."
        else:
            levels = []
            for x in raw:
                v = _number("crash_levels", x, errors)
                if v is None:
                    break
                levels.append(v)
            else:
                if len(set(levels)) != len(levels):
                    errors["crash_levels"] = "Each crash level can appear only once."
                else:
                    clean["crash_levels"] = sorted(levels)
    if errors:
        raise SettingsError(errors)
    return clean


def _bad(errors: dict[str, str]):
    from fastapi import HTTPException
    field, msg = next(iter(errors.items()))
    return HTTPException(status_code=400, detail={"code": "bad_setting", "field": field, "msg": msg, "errors": errors})


async def update(db, patch: Any) -> dict:
    """Raises 400 {code: bad_setting, field, msg, errors: {field: msg}}; nothing is saved when any value is wrong."""
    try:
        clean = validate(patch)
    except SettingsError as e:
        raise _bad(e.errors) from e
    if clean:
        await db.settings.update_one({"_id": "app"}, {"$set": clean}, upsert=True)
    _cache["value"] = None
    return await get(db)


def reset_cache() -> None:
    _cache["value"] = None
