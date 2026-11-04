"""Time helpers. Every business boundary (Runs reset on the 1st, quiet hours,
Monday 8 am) is in IST; storage is always UTC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Mongo returns naive UTC datetimes; normalise everything to aware UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def ist_month_key(now: datetime | None = None) -> str:
    return as_utc(now or utcnow()).astimezone(IST).strftime("%Y-%m")


def ist_month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """[start, end) of the current IST calendar month, as UTC datetimes."""
    local = as_utc(now or utcnow()).astimezone(IST)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start.astimezone(timezone.utc), nxt.astimezone(timezone.utc)
