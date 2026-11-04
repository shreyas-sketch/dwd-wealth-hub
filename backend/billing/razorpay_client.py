"""Razorpay Subscriptions behind one interface (docs: razorpay.com/docs/api/payments/subscriptions).

  create_subscription  POST /v1/subscriptions {plan_id, total_count, customer_notify, notes}
  fetch_subscription   GET  /v1/subscriptions/{id}
  cancel_subscription  POST /v1/subscriptions/{id}/cancel {cancel_at_cycle_end}
  Checkout signature   HMAC_SHA256(payment_id + "|" + subscription_id, key_secret)
  Webhook signature    HMAC_SHA256(raw body, webhook secret) in X-Razorpay-Signature

Two monthly plans are created once in the Razorpay dashboard (₹2,000 and ₹5,000 — decide whether
these include 18% GST) and their ids set as RAZORPAY_PLAN_LITE / RAZORPAY_PLAN_PRO.
# NEEDS: keys + plan ids (from Bullzeye billing/razorpay_client.py, plan ids changed)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Optional, Protocol

import httpx

API = "https://api.razorpay.com/v1"
TOTAL_COUNT = {"monthly": 120, "yearly": 10}


class RazorpayError(Exception):
    pass


def plan_id_for(plan: str, period: str = "monthly") -> Optional[str]:
    return os.environ.get({("lite", "monthly"): "RAZORPAY_PLAN_LITE",
                           ("pro", "monthly"): "RAZORPAY_PLAN_PRO"}.get((plan, period), "_"))


def hmac_hex(secret: str, msg: bytes) -> str:
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


class Razorpay(Protocol):
    mode: str
    key_id: str

    async def create_subscription(self, plan: str, period: str, notes: dict) -> dict: ...
    async def fetch_subscription(self, sub_id: str) -> dict: ...
    async def cancel_subscription(self, sub_id: str, at_cycle_end: bool = True) -> dict: ...
    def verify_payment(self, payment_id: str, sub_id: str, signature: str) -> bool: ...
    def verify_webhook(self, body: bytes, signature: str) -> bool: ...


class LiveRazorpay:
    mode = "live"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str, client: Optional[httpx.AsyncClient] = None):
        self.key_id, self._secret, self._wh, self._client = key_id, key_secret, webhook_secret, client

    async def _req(self, method: str, path: str, **kw) -> dict:
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            r = await client.request(method, API + path, auth=(self.key_id, self._secret), **kw)
        finally:
            if self._client is None:
                await client.aclose()
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            raise RazorpayError(f"{path}: HTTP {r.status_code} {(body.get('error') or {}).get('description', '')}")
        return body

    async def create_subscription(self, plan, period, notes) -> dict:
        pid = plan_id_for(plan, period)
        if not pid:
            raise RazorpayError(f"no Razorpay plan id set for {plan}/{period}")
        return await self._req("POST", "/subscriptions", json={
            "plan_id": pid, "total_count": TOTAL_COUNT[period], "quantity": 1, "customer_notify": 1,
            "notes": {k: str(v)[:250] for k, v in notes.items()}})

    async def fetch_subscription(self, sub_id) -> dict:
        return await self._req("GET", f"/subscriptions/{sub_id}")

    async def cancel_subscription(self, sub_id, at_cycle_end=True) -> dict:
        return await self._req("POST", f"/subscriptions/{sub_id}/cancel",
                               json={"cancel_at_cycle_end": 1 if at_cycle_end else 0})

    async def pause_subscription(self, sub_id) -> dict:
        return await self._req("POST", f"/subscriptions/{sub_id}/pause", json={"pause_at": "now"})

    async def resume_subscription(self, sub_id) -> dict:
        return await self._req("POST", f"/subscriptions/{sub_id}/resume", json={"resume_at": "now"})

    def verify_payment(self, payment_id, sub_id, signature) -> bool:
        return hmac.compare_digest(hmac_hex(self._secret, f"{payment_id}|{sub_id}".encode()), signature or "")

    def verify_webhook(self, body, signature) -> bool:
        return hmac.compare_digest(hmac_hex(self._wh, body), signature or "")


class FakeRazorpay:
    """Fake Razorpay for tests and QA. Same signatures, so the webhook path is real."""
    mode = "fake"
    key_id = "rzp_test_fake"
    key_secret = "fake_secret"
    webhook_secret = "fake_webhook_secret"
    subs: dict = {}

    async def create_subscription(self, plan, period, notes) -> dict:
        sid = "sub_" + secrets.token_hex(7)
        self.subs[sid] = {"id": sid, "entity": "subscription", "status": "created", "plan": plan, "period": period,
                          "notes": notes, "paid_count": 0, "current_start": None, "current_end": None,
                          "short_url": f"https://rzp.io/fake/{sid}"}
        return dict(self.subs[sid])

    async def fetch_subscription(self, sub_id) -> dict:
        if sub_id not in self.subs:
            raise RazorpayError("not found")
        return dict(self.subs[sub_id])

    async def cancel_subscription(self, sub_id, at_cycle_end=True) -> dict:
        self.subs[sub_id]["status"] = "active" if at_cycle_end else "cancelled"
        self.subs[sub_id]["cancel_at_cycle_end"] = at_cycle_end
        return dict(self.subs[sub_id])

    async def pause_subscription(self, sub_id) -> dict:
        self.subs[sub_id]["status"] = "paused"
        return dict(self.subs[sub_id])

    async def resume_subscription(self, sub_id) -> dict:
        self.subs[sub_id]["status"] = "active"
        return dict(self.subs[sub_id])

    def verify_payment(self, payment_id, sub_id, signature) -> bool:
        return hmac.compare_digest(hmac_hex(self.key_secret, f"{payment_id}|{sub_id}".encode()), signature or "")

    def verify_webhook(self, body, signature) -> bool:
        return hmac.compare_digest(hmac_hex(self.webhook_secret, body), signature or "")

    def charge_event(self, sub_id: str, amount_paise: int, *, method: str = "upi", vpa: Optional[str] = None,
                     now: Optional[float] = None) -> dict:
        """What Razorpay would POST for subscription.charged."""
        s = self.subs[sub_id]
        now = now or time.time()
        s["paid_count"] += 1
        s["status"] = "active"
        s["current_start"] = int(now)
        s["current_end"] = int(now + (366 if s["period"] == "yearly" else 31) * 86400)
        pay = {"id": "pay_" + secrets.token_hex(7), "entity": "payment", "amount": amount_paise, "currency": "INR",
               "status": "captured", "method": method, "vpa": vpa, "subscription_id": sub_id,
               "created_at": int(now)}
        return {"event": "subscription.charged", "payload": {"subscription": {"entity": dict(s)},
                                                             "payment": {"entity": pay}},
                "created_at": int(now)}


def build_client() -> Optional[Razorpay]:
    from core.vendors import vendor_mode
    mode = vendor_mode("razorpay")
    if mode == "fake":
        return FakeRazorpay()
    if mode == "live":
        return LiveRazorpay(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"],
                            os.environ["RAZORPAY_WEBHOOK_SECRET"])
    return None
