"""Billing: Razorpay Subscriptions (monthly).

subscriptions {_id: sub_id, user_id, plan lite|pro, status created|active|cancelled|halted|completed,
               current_end, cancel_at_cycle_end, created_at, updated_at}

POST /api/billing/checkout {plan}       → open Razorpay Checkout with subscription_id (fake mode: confirm with /verify)
POST /api/billing/verify {...}          → provisional access until the webhook confirms (2 days if unconfirmed)
POST /api/billing/cancel                → cancels at the end of the paid month
POST /api/billing/razorpay/webhook      → subscription.activated / charged / cancelled / halted / completed
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import plans
from core.deps import user_dep
from core.settings import settings
from growth import events
from growth.clock import as_utc, utcnow
from state import db

from .razorpay_client import RazorpayError, build_client

log = logging.getLogger("billing")
router = APIRouter(prefix="/billing", tags=["billing"])
PROVISIONAL_DAYS = 2


class CheckoutIn(BaseModel):
    plan: Literal["lite", "pro"]


class VerifyIn(BaseModel):
    subscription_id: str = Field(..., max_length=64)
    payment_id: str = Field("", max_length=64)
    signature: str = Field("", max_length=200)


def _client():
    c = build_client()
    if c is None:
        raise HTTPException(status_code=503, detail={"code": "billing_off", "msg": "Payments aren't set up yet."})
    return c


@router.post("/checkout")
async def checkout(body: CheckoutIn, user: dict = Depends(user_dep())):
    c = _client()
    uid = str(user["_id"])
    try:
        sub = await c.create_subscription(body.plan, "monthly", {"user_id": uid, "plan": body.plan})
    except RazorpayError as e:
        log.warning("checkout failed: %s", e)
        raise HTTPException(status_code=502, detail={"code": "checkout_failed", "msg": "Couldn't start the payment. Try again."})
    now = utcnow()
    await db().subscriptions.insert_one({"_id": sub["id"], "user_id": uid, "plan": body.plan, "status": "created",
                                         "current_end": None, "cancel_at_cycle_end": False, "created_at": now,
                                         "updated_at": now})
    await events.track(db(), "checkout_started", user_id=uid, props={"plan": body.plan})
    return {"mode": c.mode, "subscription_id": sub["id"], "key_id": getattr(c, "key_id", None),
            "amount_inr": plans.total_inr(body.plan), "price_inr": plans.PRICES_INR[body.plan],
            "gst_inr": plans.total_inr(body.plan) - plans.PRICES_INR[body.plan], "plan": body.plan, "name": settings.brand_name,
            "description": plans.LABELS[body.plan], "prefill": {"contact": user.get("phone"), "email": user.get("email")}}


async def _activate(sub_id: str, current_end: datetime, *, paid: bool, amount_inr=None) -> None:
    s = await db().subscriptions.find_one({"_id": sub_id})
    if not s:
        return
    prev_end = s.get("current_end")
    end = max(as_utc(prev_end), current_end) if prev_end else current_end
    await db().subscriptions.update_one({"_id": sub_id}, {"$set": {"status": "active", "current_end": end,
                                                                    "updated_at": utcnow(), "confirmed": paid or s.get("confirmed", False)}})
    if paid:
        await events.track(db(), "payment_captured", user_id=s["user_id"], props={"plan": s["plan"], "amount_inr": amount_inr})
    if not s.get("activated_event"):
        await db().subscriptions.update_one({"_id": sub_id}, {"$set": {"activated_event": True}})
        await events.track(db(), "subscription_activated", user_id=s["user_id"], props={"plan": s["plan"]})
        await _end_older_subscriptions(s)


async def _end_older_subscriptions(new: dict) -> None:
    """An upgrade (₹2,000 → ₹5,000) starts a second Razorpay subscription. Stop the old one renewing, or the
    member is charged for both every month. The old one still runs to the end of the month already paid."""
    async for old in db().subscriptions.find({"user_id": new["user_id"], "_id": {"$ne": new["_id"]},
                                              "status": {"$in": ["active", "authenticated", "pending"]},
                                              "cancel_at_cycle_end": {"$ne": True}}):
        try:
            c = build_client()
            if c is not None:
                await c.cancel_subscription(old["_id"], at_cycle_end=True)
        except Exception:  # noqa: BLE001 — never block the new plan; the admin can cancel by hand
            log.warning("could not stop old subscription %s", old["_id"], exc_info=True)
            continue
        await db().subscriptions.update_one({"_id": old["_id"]}, {"$set": {"cancel_at_cycle_end": True,
                                                                             "replaced_by": new["_id"],
                                                                             "updated_at": utcnow()}})


@router.post("/verify")
async def verify(body: VerifyIn, user: dict = Depends(user_dep())):
    c = _client()
    s = await db().subscriptions.find_one({"_id": body.subscription_id, "user_id": str(user["_id"])})
    if not s:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Payment not found."})
    if c.mode == "fake":
        await _activate(s["_id"], utcnow() + timedelta(days=31), paid=True, amount_inr=plans.total_inr(s["plan"]))
    else:
        if not c.verify_payment(body.payment_id, body.subscription_id, body.signature):
            raise HTTPException(status_code=400, detail={"code": "bad_signature", "msg": "Payment couldn't be verified."})
        await _activate(s["_id"], utcnow() + timedelta(days=PROVISIONAL_DAYS), paid=False)
    return {"plan": await plans.plan_info(db(), user)}


@router.post("/cancel")
async def cancel(user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    s = await db().subscriptions.find_one({"user_id": uid, "status": "active", "cancel_at_cycle_end": {"$ne": True}},
                                          sort=[("current_end", -1)])
    if not s:
        raise HTTPException(status_code=404, detail={"code": "no_subscription", "msg": "No active subscription."})
    try:
        await _client().cancel_subscription(s["_id"], at_cycle_end=True)
    except RazorpayError as e:
        log.warning("cancel failed: %s", e)
        raise HTTPException(status_code=502, detail={"code": "cancel_failed", "msg": "Couldn't cancel right now. Try again."})
    await db().subscriptions.update_one({"_id": s["_id"]}, {"$set": {"cancel_at_cycle_end": True, "updated_at": utcnow()}})
    await events.track(db(), "subscription_cancelled", user_id=uid)
    end = s.get("current_end")
    return {"status": "cancels_at_period_end", "access_until": as_utc(end).isoformat() if end else None}


@router.post("/razorpay/webhook")
async def webhook(request: Request):
    c = build_client()
    raw = await request.body()
    if c is None or not c.verify_webhook(raw, request.headers.get("X-Razorpay-Signature", "")):
        raise HTTPException(status_code=400, detail={"code": "bad_signature", "msg": "bad signature"})
    ev = json.loads(raw or b"{}")
    name = ev.get("event", "")
    sub = ((ev.get("payload") or {}).get("subscription") or {}).get("entity") or {}
    sid = sub.get("id")
    if not sid:
        return {"ok": True}
    if name in ("subscription.activated", "subscription.charged", "subscription.resumed"):
        end = sub.get("current_end")
        end_dt = datetime.fromtimestamp(end, tz=timezone.utc) if end else utcnow() + timedelta(days=31)
        pay = ((ev.get("payload") or {}).get("payment") or {}).get("entity") or {}
        await _activate(sid, end_dt, paid=name == "subscription.charged",
                        amount_inr=(pay.get("amount") or 0) / 100 if pay else None)
    elif name in ("subscription.cancelled", "subscription.halted", "subscription.completed", "subscription.paused"):
        await db().subscriptions.update_one({"_id": sid}, {"$set": {"status": name.split(".")[1], "updated_at": utcnow()}})
    return {"ok": True}
