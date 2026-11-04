"""Tax ledger (from Bullzeye; kept silently in the background — not a product feature here).

Every acquisition, disposal and yield receipt is written as it happens:
  tax_ledger {user_id, ts, fy, venue, kind acquisition|disposal|income,
              coin, qty, price_usd, value_usd, usd_inr, value_inr, fx_source,
              cost_inr (disposal), gain_inr, taxable_gain_inr, tax_30_inr,
              tds_1pct_flag, tds_estimate_inr, ref, note}
  tax_lots   FIFO cost lots per user+coin {qty_left, cost_inr_per_unit}

India VDA rules as built (for the user's CA; shown as estimates):
  * 30% on each disposal's gain; a loss on one VDA is NOT set off against
    another (so taxable gain = max(gain, 0) per disposal) — §115BBH.
  * 1% TDS on the consideration of each transfer — deducted by the exchange's
    Indian entity (§194S); we flag it and estimate it, we don't deduct it.
  * Yield received (dual-investment interest, grid profit already counted on
    the disposal) is recorded as `income` at market value on receipt.
USDT and other stablecoins are VDAs too, so conversions into USDT are disposals.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from growth.clock import IST, as_utc, utcnow

TDS_NOTE = ("Crypto gains are taxed at 30% in India, and transfers may attract 1% TDS. This ledger records "
            "buys made by the app for your CA — nothing here is tax advice.")
from .fx import usd_inr

TAX_RATE = 0.30
TDS_RATE = 0.01


def fy_of(ts: datetime) -> str:
    d = as_utc(ts).astimezone(IST)
    y = d.year if d.month >= 4 else d.year - 1
    return f"FY{y}-{str(y + 1)[-2:]}"


async def _consume_lots(db, uid: str, coin: str, qty: float) -> float:
    """FIFO cost in INR for `qty` units; missing lots count at zero cost (conservative)."""
    cost, need = 0.0, qty
    async for lot in db.tax_lots.find({"user_id": uid, "coin": coin, "qty_left": {"$gt": 0}}).sort("ts", 1):
        take = min(need, lot["qty_left"])
        cost += take * lot["cost_inr_per_unit"]
        await db.tax_lots.update_one({"_id": lot["_id"]}, {"$inc": {"qty_left": -take}})
        need -= take
        if need <= 1e-12:
            break
    return cost


async def record(db, uid: str, kind: str, coin: str, qty: float, price_usd: float, *, venue: str, ref: str,
                 ts: Optional[datetime] = None, note: str = "") -> Optional[dict]:
    """Idempotent on (ref, kind, coin)."""
    if qty <= 0:
        return None
    ts = ts or utcnow()
    _id = f"{uid}:{ref}:{kind}:{coin}"
    if await db.tax_ledger.find_one({"_id": _id}):
        return None
    rate, fx_source = await usd_inr(db, ts)
    value_usd = qty * price_usd
    row = {"_id": _id, "user_id": uid, "ts": ts, "at": ts, "fy": fy_of(ts), "venue": venue, "kind": kind,
           "event": {"acquisition": "acquire", "disposal": "dispose", "income": "income"}[kind],
           "coin": coin, "asset": coin, "qty": qty, "price_usd": price_usd, "value_usd": round(value_usd, 6),
           "usd_inr": rate, "value_inr": round(value_usd * rate, 2), "consideration_inr": round(value_usd * rate, 2),
           "fx_source": fx_source, "ref": ref, "position_id": ref, "note": note,
           "tds_applicable": kind == "disposal", "tds_note": TDS_NOTE if kind == "disposal" else None}
    if kind in ("acquisition", "income"):
        await db.tax_lots.insert_one({"_id": f"lot:{_id}", "user_id": uid, "coin": coin, "ts": ts,
                                      "qty_left": qty, "cost_inr_per_unit": price_usd * rate})
    elif kind == "disposal":
        cost = await _consume_lots(db, uid, coin, qty)
        gain = row["value_inr"] - cost
        row.update(gain_usd=round(gain / rate, 2), taxable_gain_usd=round(max(gain, 0) / rate, 2),
                   tax_30_usd=round(max(gain, 0) * TAX_RATE / rate, 2), tds_estimate_usd=round(value_usd * TDS_RATE, 2))
        row.update(cost_inr=round(cost, 2), cost_basis_inr=round(cost, 2), gain_inr=round(gain, 2), taxable_gain_inr=round(max(gain, 0), 2),
                   tax_30_inr=round(max(gain, 0) * TAX_RATE, 2), tds_1pct_flag=True,
                   tds_estimate_inr=round(row["value_inr"] * TDS_RATE, 2))
    await db.tax_ledger.insert_one(row)
    return row


async def summary(db, uid: str, fy: Optional[str] = None) -> dict:
    fy = fy or fy_of(utcnow())
    out = {"fy": fy, "disposals": 0, "gains_inr": 0.0, "losses_inr_not_set_off": 0.0, "taxable_gain_inr": 0.0,
           "tax_30_inr": 0.0, "tds_estimate_inr": 0.0, "income_inr": 0.0, "rows": 0,
           "taxable_gain_usd": 0.0, "tax_30_usd": 0.0, "tds_estimate_usd": 0.0, "income_usd": 0.0,
           "losses_usd_not_set_off": 0.0,
           "note": "Estimates for your CA: 30% on each gain, losses not set off, 1% TDS deducted by the exchange."}
    async for r in db.tax_ledger.find({"user_id": uid, "fy": fy}):
        out["rows"] += 1
        if r["kind"] == "disposal":
            out["disposals"] += 1
            g = r.get("gain_inr", 0)
            out["gains_inr" if g >= 0 else "losses_inr_not_set_off"] += abs(g)
            out["taxable_gain_inr"] += r.get("taxable_gain_inr", 0)
            out["tax_30_inr"] += r.get("tax_30_inr", 0)
            out["tds_estimate_inr"] += r.get("tds_estimate_inr", 0)
            out["taxable_gain_usd"] += r.get("taxable_gain_usd", 0)
            out["tax_30_usd"] += r.get("tax_30_usd", 0)
            out["tds_estimate_usd"] += r.get("tds_estimate_usd", 0)
            if r.get("gain_usd", 0) < 0:
                out["losses_usd_not_set_off"] += -r["gain_usd"]
        elif r["kind"] == "income":
            out["income_inr"] += r["value_inr"]
            out["income_usd"] += r["value_usd"]
    return {k: round(v, 2) if isinstance(v, float) else v for k, v in out.items()}


COLUMNS = ["date_ist", "fy", "venue", "event", "asset", "qty", "price_usd", "value_usd", "gain_usd",
           "usd_inr", "consideration_inr", "fx_source", "cost_basis_inr", "gain_inr", "taxable_gain_inr",
           "tax_30_inr", "tds_applicable", "tds_estimate_inr", "position_id", "note"]   # USD first; INR for the CA


async def csv_export(db, uid: str, fy: Optional[str] = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    q = {"user_id": uid, **({"fy": fy} if fy else {})}
    async for r in db.tax_ledger.find(q).sort("ts", 1):
        w.writerow([as_utc(r["ts"]).astimezone(IST).strftime("%Y-%m-%d %H:%M")] + [r.get(c, "") for c in COLUMNS[1:]])
    return buf.getvalue()
