"""One-off data fixes that run at startup (server.create_app, under the startup lock, so once per deploy).

Each fix is idempotent: on a database that is already clean it changes nothing. Add new fixes at the end and keep
old ones; they cost one indexed query each.
"""
from __future__ import annotations

import logging

log = logging.getLogger("maintenance")

LEGACY_FAILED_XRAY = "Couldn't check right now"


async def fix_legacy_radar_checks(db) -> int:
    """Before 10 Nov a failed radar X-Ray was saved as Risky 50 with the flag "Couldn't check right now". Mark those
    as unchecked so they show "Not checked yet" and the next scan retries them."""
    res = await db.radar_items.update_many({"xray.red_flags": LEGACY_FAILED_XRAY},
                                           {"$set": {"xray": {"label": "unchecked", "score": None, "red_flags": []}}})
    return res.modified_count


async def drop_non_coin_verdicts(db) -> int:
    """Remove verdicts (and their hit-rate rows) for things that were never plain coins, e.g. FIGR_HELOC, a tokenised
    loan that entered the top 10 before the filter existed, and privacy coins such as XMR (Monero)."""
    from market import is_plain_coin
    bad = [s for s in await db.verdicts.distinct("symbol") if not is_plain_coin({"symbol": s})]
    if not bad:
        return 0
    res = await db.verdicts.delete_many({"symbol": {"$in": bad}})
    await db.verdict_outcomes.delete_many({"symbol": {"$in": bad}})
    log.info("removed verdicts for non-coins: %s", ", ".join(bad))
    return res.deleted_count


OLD_CLAIM = "Big, liquid coin listed on every major exchange."
NEW_CLAIM = "One of the largest coins by market value, so it trades a lot every day."


async def reword_exchange_claim(db) -> int:
    """Stored verdicts carried a filler point claiming "listed on every major exchange", which the app never checked.
    It appears in the "case for" list and, when it was the first point, inside the chair's sentence too."""
    n = 0
    flt = {"$or": [{"bull": OLD_CLAIM}, {"chair": {"$regex": "listed on every major exchange"}}]}
    async for v in db.verdicts.find(flt, {"bull": 1, "chair": 1}):
        upd = {"bull": [NEW_CLAIM if b == OLD_CLAIM else b for b in (v.get("bull") or [])]}
        if isinstance(v.get("chair"), str):
            upd["chair"] = v["chair"].replace(OLD_CLAIM, NEW_CLAIM)
        await db.verdicts.update_one({"_id": v["_id"]}, {"$set": upd})
        n += 1
    return n


FIXES = [fix_legacy_radar_checks, drop_non_coin_verdicts, reword_exchange_claim]


async def run_data_fixes(db) -> dict:
    out = {}
    for fix in FIXES:
        try:
            n = await fix(db)
        except Exception:  # noqa: BLE001 — a failed fix must never stop the app starting
            log.warning("data fix %s failed", fix.__name__, exc_info=True)
            continue
        if n:
            out[fix.__name__] = n
            log.info("data fix %s changed %d rows", fix.__name__, n)
    return out
