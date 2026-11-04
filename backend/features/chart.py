"""Chart Reader (₹2,000: 10 a month; ₹5,000: unlimited).

POST /api/chart  multipart: file (+ symbol)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import plans
from core.deps import user_dep
from features import DISCLAIMER
from growth import events
from state import db

from .chart_vision import MAX_BYTES, ChartError, analyze_chart

router = APIRouter(tags=["chart"])


@router.post("/chart")
async def read_chart(file: UploadFile = File(...), symbol: Optional[str] = Form(None), user: dict = Depends(user_dep())):
    plan = await plans.require(db(), user, "chart")
    data = await file.read(MAX_BYTES + 1)
    sym = (symbol or "").strip().upper()[:15]
    usage = await plans.consume(db(), user, "chart", plan)
    try:
        out = await analyze_chart(data, sym)
    except ChartError as e:
        await plans.refund(db(), user, "chart")
        # "unavailable" = the AI is busy or slow (not the user's fault): 503 so the app says "try again in a minute"
        if e.code == "unavailable":
            raise HTTPException(status_code=503, detail={"code": e.code, "msg": e.msg, "retry_after": e.retry_after or 15},
                                headers={"Retry-After": str(e.retry_after or 15)})
        raise HTTPException(status_code=400, detail={"code": e.code, "msg": e.msg})
    if not out.get("is_chart"):
        await plans.refund(db(), user, "chart")
        raise HTTPException(status_code=400, detail={"code": "not_chart",
                                                     "msg": "That doesn't look like a price chart. Try a screenshot of a candle or line chart."})
    await events.track(db(), "chart_read", user_id=str(user["_id"]))
    return {"is_chart": True, "symbol": out.get("symbol") or sym or None, "timeframe": out.get("timeframe"),
            "trend": out.get("trend"), "summary": out.get("summary"), "support": out.get("support") or [],
            "resistance": out.get("resistance") or [], "rsi_read": out.get("rsi_read"),
            "patterns": out.get("patterns") or [], "what_to_watch": out.get("what_to_watch") or [],
            "usage": usage, "disclaimer": DISCLAIMER}
