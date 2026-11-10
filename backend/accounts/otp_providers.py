"""OTP delivery providers behind one interface.

    WhatsApp  — AiSensy API campaign on the approved Authentication template
                `AISENSY_OTP_CAMPAIGN` (Meta fixes the body: "<code> is your
                verification code", plus a Copy-code button).
    SMS       — MSG91 OTP API v5 on the DLT-registered template. We pass our
                own code (`otp=`), so verification stays in our database and
                behaves the same whichever channel delivered the code.
    Console   — development only: logs the code. Refused in production.

A new provider is one class with `channel`, `name` and `async send()`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

import httpx

from core.http import shared_client

log = logging.getLogger("accounts.otp_providers")

AISENSY_URL = "https://backend.aisensy.com/campaign/t1/api/v2"
MSG91_OTP_URL = "https://control.msg91.com/api/v5/otp"


@dataclass
class SendResult:
    ok: bool
    provider: str
    channel: str
    ref: Optional[str] = None
    error: Optional[str] = None


class OtpSender(Protocol):
    channel: str
    name: str

    async def send(self, phone_e164: str, code: str, ttl_min: int) -> SendResult: ...


class AiSensyWhatsApp:
    channel, name = "whatsapp", "aisensy"

    def __init__(self, api_key: str, campaign: str, client: httpx.AsyncClient | None = None):
        self.api_key, self.campaign, self._client = api_key, campaign, client

    async def send(self, phone_e164: str, code: str, ttl_min: int) -> SendResult:
        payload = {
            "apiKey": self.api_key,
            "campaignName": self.campaign,
            "destination": phone_e164.lstrip("+"),
            "userName": os.environ.get("BRAND_NAME", "Coinzeye") + " user",
            "source": "otp",
            "templateParams": [code],
            # Authentication templates carry the code again on the Copy-code button.
            "buttons": [{"type": "button", "sub_type": "url", "index": 0,
                         "parameters": [{"type": "text", "text": code}]}],
        }
        try:
            r = await (self._client or shared_client()).post(AISENSY_URL, json=payload, timeout=10)
            body = r.json() if r.content else {}
            if r.status_code == 200 and (body.get("success") in (True, "true") or "submitted_message_id" in body):
                return SendResult(True, self.name, self.channel, ref=str(body.get("submitted_message_id") or ""))
            return SendResult(False, self.name, self.channel, error=f"HTTP {r.status_code}: {str(body)[:200]}")
        except Exception as e:  # noqa: BLE001
            return SendResult(False, self.name, self.channel, error=f"{type(e).__name__}: {e}")


class Msg91Sms:
    channel, name = "sms", "msg91"

    def __init__(self, auth_key: str, template_id: str, client: httpx.AsyncClient | None = None):
        self.auth_key, self.template_id, self._client = auth_key, template_id, client

    async def send(self, phone_e164: str, code: str, ttl_min: int) -> SendResult:
        params = {"template_id": self.template_id, "mobile": phone_e164.lstrip("+"),
                  "otp": code, "otp_expiry": str(ttl_min)}
        try:
            r = await (self._client or shared_client()).post(MSG91_OTP_URL, params=params, timeout=10,
                                                            headers={"authkey": self.auth_key, "accept": "application/json"})
            body = r.json() if r.content else {}
            if r.status_code == 200 and body.get("type") == "success":
                return SendResult(True, self.name, self.channel, ref=body.get("request_id"))
            return SendResult(False, self.name, self.channel, error=f"HTTP {r.status_code}: {str(body)[:200]}")
        except Exception as e:  # noqa: BLE001
            return SendResult(False, self.name, self.channel, error=f"{type(e).__name__}: {e}")


class ConsoleSender:
    """Dev/test only — prints the code to the server log."""

    def __init__(self, channel: str = "sms"):
        self.channel, self.name = channel, "console"
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone_e164: str, code: str, ttl_min: int) -> SendResult:
        self.sent.append((phone_e164, code))
        log.warning("DEV OTP for %s: %s", phone_e164, code)
        return SendResult(True, self.name, self.channel, ref="console")


@dataclass
class Senders:
    whatsapp: Optional[OtpSender]
    sms: Optional[OtpSender]


def clean_secret(name: str) -> str:
    """A key as pasted into a dashboard: drop surrounding whitespace, line breaks and quotes, which providers would
    otherwise reject as a wrong key (HTTP 401)."""
    return (os.environ.get(name) or "").strip().strip("\"'").strip()


def build_senders() -> Senders:
    """Reads env. WhatsApp is used only when the WHATSAPP_OTP flag is on (Admin › Features,
    or OTP_WHATSAPP_ENABLED=true) and AISENSY_API_KEY is set; otherwise SMS (MSG91).
    QA_MODE uses the console sender."""
    from core.settings import settings
    mode = os.environ.get("OTP_PROVIDER_MODE", "console" if settings.qa_mode else "live").lower()
    if mode == "console":
        if settings.is_production:
            raise RuntimeError("OTP_PROVIDER_MODE=console is not allowed in production")
        return Senders(whatsapp=ConsoleSender("whatsapp"), sms=ConsoleSender("sms"))
    from core.flags import is_on
    sms = None
    if os.environ.get("MSG91_AUTH_KEY") and os.environ.get("MSG91_OTP_TEMPLATE_ID"):
        sms = Msg91Sms(clean_secret("MSG91_AUTH_KEY"), clean_secret("MSG91_OTP_TEMPLATE_ID"))
    wa = None
    # The WhatsApp OTP switch chooses WhatsApp over SMS. When SMS isn't set up at all, WhatsApp is the only way in,
    # so it is used whatever the switch says (turning the switch off must never lock everyone out).
    if os.environ.get("AISENSY_API_KEY") and (is_on("WHATSAPP_OTP") or sms is None):
        wa = AiSensyWhatsApp(clean_secret("AISENSY_API_KEY"), clean_secret("AISENSY_OTP_CAMPAIGN") or "otp")
    if wa is None and sms is None:
        log.error("No OTP provider configured (MSG91_* / AISENSY_*). Logins will fail.")
    return Senders(whatsapp=wa, sms=sms)
