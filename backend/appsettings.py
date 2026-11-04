"""Admin-editable app settings (one Mongo document, cached briefly).

    settings {_id: "app", trial_days, scenario_rates: {bad, average, good}, crash_levels, anon_xray_per_day}
"""
from __future__ import annotations

import time
from copy import deepcopy

DEFAULTS: dict = {
    "trial_days": 3,                                   # new accounts get the ₹5,000 plan as a trial (webinar → Day 3 call)
    "scenario_rates": {"bad": 0.0, "average": 15.0, "good": 35.0},   # % a year — labelled assumptions in My Crypto Plan
    "crash_levels": [20, 30, 40],                      # BTC fall from its 30-day high, in %
    "anon_xray_per_day": 1,                            # Coin X-Ray checks per day without an account
}

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


def _bad(field: str, msg: str):
    from fastapi import HTTPException
    return HTTPException(status_code=400, detail={"code": "bad_setting", "field": field, "msg": msg})


async def update(db, patch: dict) -> dict:
    """Raises 400 {code: bad_setting} when a value isn't a number (the admin form sends what was typed)."""
    try:
        return await _update(db, patch)
    except (TypeError, ValueError, AttributeError) as e:
        raise _bad("settings", "Use whole numbers for days, levels and checks, and numbers for the yearly rates.") from e


async def _update(db, patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise ValueError("settings must be an object")
    clean = {}
    if "trial_days" in patch and patch["trial_days"] is not None:
        clean["trial_days"] = max(0, min(30, int(patch["trial_days"])))
    if isinstance(patch.get("scenario_rates"), dict):
        r = patch["scenario_rates"]
        clean["scenario_rates"] = {k: max(-50.0, min(100.0, float(r.get(k, DEFAULTS["scenario_rates"][k]))))
                                   for k in ("bad", "average", "good")}
    if isinstance(patch.get("crash_levels"), list):
        lv = sorted({int(x) for x in patch["crash_levels"] if 5 <= int(x) <= 90})
        clean["crash_levels"] = lv or DEFAULTS["crash_levels"]
    if "anon_xray_per_day" in patch and patch["anon_xray_per_day"] is not None:
        clean["anon_xray_per_day"] = max(0, min(20, int(patch["anon_xray_per_day"])))
    if clean:
        await db.settings.update_one({"_id": "app"}, {"$set": clean}, upsert=True)
    _cache["value"] = None
    return await get(db)


def reset_cache() -> None:
    _cache["value"] = None
