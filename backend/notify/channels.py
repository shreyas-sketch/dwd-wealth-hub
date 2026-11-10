"""WhatsApp delivery for inbox alerts (AiSensy, adapted from Bullzeye notify/channels.py).

One AiSensy API campaign per alert kind. # NEEDS: create each campaign in AiSensy once Meta
approves the template (one body param: the alert text; one URL button param: the link path).
Campaign names can be overridden by env AISENSY_CAMPAIGN_<KIND>.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx  # noqa: F401  (type hints / injected test clients)

from core.http import shared_client

log = logging.getLogger("notify.channels")
AISENSY_URL = "https://backend.aisensy.com/campaign/t1/api/v2"


def campaign_for(kind: str) -> str:
    return os.environ.get(f"AISENSY_CAMPAIGN_{kind.upper()}", f"alert_{kind}")


@dataclass
class Sent:
    ok: bool
    ref: Optional[str] = None
    error: Optional[str] = None


def _one_line(s: str, n: int = 900) -> str:
    """Meta rejects template params with newlines, tabs or 4+ spaces."""
    return " ".join(str(s or "").split())[:n] or "-"


class AiSensyWhatsApp:
    name = "whatsapp"

    def __init__(self, api_key: str, client: Optional[httpx.AsyncClient] = None):
        self.api_key, self._client = api_key, client

    async def send(self, user: dict, row: dict) -> Sent:
        phone = user.get("phone")
        if not phone:
            return Sent(False, error="no phone")
        payload = {
            "apiKey": self.api_key, "campaignName": campaign_for(row["kind"]),
            "destination": phone.lstrip("+"),
            "userName": (user.get("name") or os.environ.get("BRAND_NAME", "Coinzeye") + " user")[:60],
            "source": f"alert-{row['kind']}",
            "templateParams": [_one_line(f"{row['title']} — {row['body']}")],
            "buttons": [{"type": "button", "sub_type": "url", "index": 0,
                         "parameters": [{"type": "text", "text": (row.get("link") or "/app").lstrip("/")}]}],
        }
        try:
            r = await (self._client or shared_client()).post(AISENSY_URL, json=payload, timeout=15)
            body = r.json() if r.content else {}
            if r.status_code == 200 and (body.get("success") in (True, "true") or "submitted_message_id" in body):
                return Sent(True, ref=str(body.get("submitted_message_id") or ""))
            return Sent(False, error=f"HTTP {r.status_code}: {str(body)[:200]}")
        except Exception as e:  # noqa: BLE001
            return Sent(False, error=f"{type(e).__name__}: {e}")


class FakeChannel:
    name = "whatsapp"

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    async def send(self, user: dict, row: dict) -> Sent:
        if not user.get("phone"):
            return Sent(False, error="no phone")
        self.sent.append((str(user["_id"]), row))
        return Sent(True, ref=f"fake-{len(self.sent)}")


def build_whatsapp():
    from core.vendors import vendor_mode
    mode = vendor_mode("aisensy")
    if mode == "fake":
        return FakeChannel()
    if mode == "live":
        from accounts.otp_providers import clean_secret
        return AiSensyWhatsApp(clean_secret("AISENSY_API_KEY"))
    return None
