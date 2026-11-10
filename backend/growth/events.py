"""The single event table (from Bullzeye).

Every funnel step, message, tool run and payment lands here as one row:
    {_id, name, ts, user_id?, anon_id?, props, src}
Admin pulse, webinar report and usage charts read this collection. Names are a closed registry so a typo cannot
silently create a new metric.

Server code calls `track(db, name, ...)`. The browser posts to POST /api/events,
which accepts only the CLIENT_EVENTS subset (views and clicks); anything that
means money or a tool run is recorded server-side only.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from .clock import utcnow

log = logging.getLogger("growth.events")

EVENTS: dict[str, str] = {
    # acquisition & auth
    "page_view": "Any page view (props.path)",
    "otp_requested": "OTP sent (props.channel)",
    "otp_failed": "OTP send or verify failed (props.reason)",
    "signup": "New account created by OTP (props.source)",
    "login": "Existing account logged in",
    "staff_login": "Staff email login",
    # tools
    "tool_opened": "A tool screen opened (props.tool) — client",
    "whatif_run": "What If calculated (props.coin, monthly_inr, years, anon)",
    "xray_run": "Coin X-Ray check (props.kind, label, anon)",
    "verdicts_viewed": "Crypto Verdicts opened",
    "forecast_run": "Forecast run (props.symbol, horizon)",
    "debate_run": "Debate run (props.symbol)",
    "watchlist_added": "Coin starred (props.symbol)",
    "watchlist_removed": "Coin unstarred (props.symbol)",
    "plan_saved": "Crypto plan saved (props.risk)",
    "paper_started": "Paper Money started from a plan",
    "paper_trade": "Paper trade (props.symbol, side)",
    "paper_rebalanced": "Paper Money rebalanced to its plan's current split",
    "airdrop_step": "Airdrop step ticked (props.airdrop)",
    "chart_read": "Chart Reader run",
    "ask_asked": "Ask Deepak question",
    "basket_practice": "Basket bought in Paper Money (props.basket)",
    "basket_invest": "Basket bought on an exchange (props.basket, total_inr)",
    "radar_viewed": "Early Coin Radar opened",
    "calendar_viewed": "Events Calendar opened",
    "p2p_viewed": "P2P rates opened",
    "news_viewed": "News Decoder opened",
    "news_checked": "Real-or-hype check",
    "limit_hit": "A metered feature hit its monthly limit (props.feature, plan)",
    "locked_hit": "A locked feature was tried (props.feature, plan)",
    # exchange rails (from Bullzeye)
    "earn_link_started": "Exchange link attempted (props.venue)",
    "earn_link_succeeded": "Exchange key linked (props.venue)",
    "earn_link_rejected": "Key refused at link time (props.venue, reason)",
    "earn_unlinked": "Exchange link removed; key material wiped",
    "earn_permission_audit_failed": "Daily key re-check failed; key wiped",
    "earn_venue_call_failed": "An exchange call failed 3 times (props.job, venue)",
    "dca_plan_saved": "Autopilot plan created or changed",
    "dca_bought": "Autopilot buy executed",
    "dca_failed": "Autopilot buy failed (props.reason)",
    # money
    "upgrade_viewed": "Upgrade prompt or plans page shown (props.surface) — client",
    "checkout_opened": "Checkout opened (props.plan) — client",
    "checkout_started": "Checkout created server-side (props.plan)",
    "payment_captured": "Payment captured (props.plan, amount_inr)",
    "subscription_activated": "Subscription active (props.plan)",
    "subscription_cancelled": "Subscription cancelled",
    "plan_granted": "Admin grant written (props.plan, months)",
    "trial_extended": "Admin changed a trial (props.days)",
    "share_clicked": "Share tapped (props.surface) — client",
    # messages
    "message_sent": "Inbox alert written (props.kind)",
    "feature_toggled": "Admin switched a feature (props.key, on)",
}

CLIENT_EVENTS = {"page_view", "tool_opened", "upgrade_viewed", "checkout_opened", "share_clicked"}

_ANON_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
ANON_COOKIE = "cz_anon"
_MAX_PROPS = 30


class UnknownEvent(ValueError):
    pass


def _clean_props(props: Optional[dict]) -> dict:
    out: dict[str, Any] = {}
    for k, v in list((props or {}).items())[:_MAX_PROPS]:
        if not isinstance(k, str) or k.startswith("$") or "." in k:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k[:40]] = v[:300] if isinstance(v, str) else v
        elif isinstance(v, (list, tuple)):
            out[k[:40]] = [x for x in v[:20] if isinstance(x, (str, int, float, bool))]
    return out


async def track(
    db, name: str, *, user_id: Optional[str] = None, anon_id: Optional[str] = None,
    props: Optional[dict] = None, src: str = "server", ts: Optional[datetime] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[str]:
    """Record one event. Never raises on a DB error (analytics must not break a
    user action) — but an unknown name raises, so typos fail in tests."""
    if name not in EVENTS:
        raise UnknownEvent(name)
    doc = {
        "_id": dedupe_key or str(uuid.uuid4()),
        "name": name, "ts": ts or utcnow(),
        "user_id": user_id, "anon_id": anon_id,
        "props": _clean_props(props), "src": src,
    }
    try:
        await db.events.insert_one(doc)
    except Exception as e:  # noqa: BLE001 — duplicate dedupe_key or DB hiccup
        if "duplicate" not in str(e).lower():
            log.warning("event %s not recorded: %s", name, e)
        return None
    return doc["_id"]


async def identify(db, anon_id: Optional[str], user_id: str) -> int:
    """Stitch a visitor's anonymous events onto the account they just created
    or logged into, so the funnel starts at their first visit."""
    if not anon_id or not _ANON_RE.match(anon_id):
        return 0
    res = await db.events.update_many(
        {"anon_id": anon_id, "user_id": None}, {"$set": {"user_id": user_id}}
    )
    return res.modified_count


def anon_id_from(request: Request) -> Optional[str]:
    v = request.cookies.get(ANON_COOKIE)
    return v if v and _ANON_RE.match(v) else None


def ensure_anon_cookie(request: Request, response: Response) -> str:
    """Give every visitor a first-party anonymous id (1 year)."""
    from core.settings import settings
    existing = anon_id_from(request)
    if existing:
        return existing
    anon = uuid.uuid4().hex
    response.set_cookie(ANON_COOKIE, anon, max_age=365 * 86400, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/")
    return anon


# ---------------------------------------------------------------- routes ----
router = APIRouter(tags=["events"])
_db = None


def bind_db(db) -> None:
    global _db
    _db = db


class ClientEvent(BaseModel):
    name: str
    props: dict = Field(default_factory=dict)


async def _optional_user_id(request: Request) -> Optional[str]:
    try:
        from auth import get_current_user
        user = await get_current_user(request)
        return str(user["_id"])
    except Exception:  # noqa: BLE001 — anonymous is fine here
        return None


@router.post("/events", status_code=202)
async def post_event(body: ClientEvent, request: Request, response: Response):
    if body.name not in CLIENT_EVENTS:
        return {"accepted": False, "reason": "not a client event"}
    anon = ensure_anon_cookie(request, response)
    uid = await _optional_user_id(request)
    await track(_db, body.name, user_id=uid, anon_id=anon, props=body.props, src="web")
    return {"accepted": True}
