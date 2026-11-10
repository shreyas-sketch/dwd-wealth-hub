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
    loan that entered the top 10 before the filter existed."""
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
    """Stored verdicts carried a filler point claiming "listed on every major exchange", which the app never checked."""
    n = 0
    async for v in db.verdicts.find({"bull": OLD_CLAIM}, {"bull": 1}):
        await db.verdicts.update_one({"_id": v["_id"]}, {"$set": {"bull": [NEW_CLAIM if b == OLD_CLAIM else b for b in v["bull"]]}})
        n += 1
    return n


async def plain_words_in_verdicts(db) -> int:
    """Stored verdicts quoted indicator names and raw values ("below both the EMA20 (594.9) and EMA50 (570.5)",
    "RSI is 39.9") and prices without a $ sign. Reword them the way new verdicts are written."""
    from features.verdicts import plain_out
    rx = {"$regex": r"\bRSI\b|\bEMA|(?i:\bprice[a-z]*( of| at| is| near| around| about)? \d)"}
    n = 0
    q = {"$or": [{"bull": rx}, {"bear": rx}, {"chair": rx}, {"summary": rx}]}
    async for v in db.verdicts.find(q, {"bull": 1, "bear": 1, "chair": 1, "summary": 1}):
        new = plain_out({k: v.get(k) for k in ("bull", "bear", "chair", "summary")})
        await db.verdicts.update_one({"_id": v["_id"]}, {"$set": new})
        n += 1
    return n


FIXES = [fix_legacy_radar_checks, drop_non_coin_verdicts, reword_exchange_claim, plain_words_in_verdicts]


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
