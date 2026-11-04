"""What If: "₹X a month in BTC since N years ago would be worth ₹Y today" — plus the worst start (the peak).

POST /api/whatif {monthly_inr, coin, years}  (no login)
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

import market
from auth import optional_user
from crypto.fx import usd_inr
from growth import events
from state import db

router = APIRouter(tags=["whatif"])
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class WhatIfIn(BaseModel):
    monthly_inr: float = Field(..., ge=100, le=1_000_000)
    coin: Literal["BTC", "ETH", "SOL"] = "BTC"
    years: Literal[3, 5] = 5


def _label(ym: str) -> str:
    y, m = ym.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def simulate(closes: list[tuple[str, float]], monthly_inr: float, fx: float) -> dict:
    """Buy at each month's close for every month except the last; value at the last close."""
    buys, last = closes[:-1], closes[-1][1]
    qty = invested = 0.0
    series = []
    for ym, px in buys:
        qty += monthly_inr / (px * fx)
        invested += monthly_inr
        series.append({"month": ym, "invested_inr": round(invested), "value_inr": round(qty * px * fx)})
    series.append({"month": closes[-1][0], "invested_inr": round(invested), "value_inr": round(qty * last * fx)})
    value = qty * last * fx
    return {"invested_inr": round(invested), "value_inr": round(value),
            "return_pct": round((value / invested - 1) * 100, 1) if invested else 0.0, "series": series}


async def calculate(monthly_inr: float, coin: str, years: int) -> dict:
    closes = await market.monthly_closes(coin, years)
    if len(closes) < 13:
        raise HTTPException(status_code=503, detail={"code": "no_data", "msg": "Price history isn't available right now."})
    fx, _ = await usd_inr(db())
    main = simulate(closes, monthly_inr, fx)
    # Worst start: begin at the highest monthly close in the window (keep at least 6 buys).
    window = closes[:-6]
    peak_i = max(range(len(window)), key=lambda i: window[i][1])
    worst = simulate(closes[peak_i:], monthly_inr, fx)
    return {"coin": coin, "monthly_inr": monthly_inr, "years": years, **main,
            "worst": {"start": closes[peak_i][0], "invested_inr": worst["invested_inr"], "value_inr": worst["value_inr"],
                      "return_pct": worst["return_pct"],
                      "note": f"the peak of these {years} years, the worst month to begin"},
            "note": "Past prices, not a promise of future returns. Buys at each month's closing price; fees and tax not included."}


@router.post("/whatif")
async def whatif(body: WhatIfIn, request: Request, response: Response):
    user = await optional_user(request)
    out = await calculate(body.monthly_inr, body.coin, body.years)
    anon = events.ensure_anon_cookie(request, response)
    await events.track(db(), "whatif_run", user_id=str(user["_id"]) if user else None, anon_id=anon,
                       props={"coin": body.coin, "monthly_inr": body.monthly_inr, "years": body.years, "anon": not user})
    return out
