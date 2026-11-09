"""Plain-English one-liners for job results (Admin › Jobs).

Jobs return small dicts (kept as-is in `job_runs` for debugging). `describe(name, result)` turns one into a
sentence the team can read at a glance, e.g. {"bought": 3, "failed": 1} → "3 plans bought, 1 failed."
QA 3 Nov: the Jobs screen showed raw JSON.

Adding a job: add a formatter here. Unknown jobs or shapes fall back to "key: value" pairs, never JSON.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from growth.clock import IST


def _n(v: Any, one: str, many: Optional[str] = None) -> str:
    try:
        k = int(v or 0)
    except (TypeError, ValueError):
        k = 0
    return f"{k:,} {one if k == 1 else (many or one + 's')}"


def _when(v: Any) -> Optional[str]:
    from datetime import datetime
    if not v:
        return None
    try:
        dt = v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
        local = dt.astimezone(IST)
        return f"{local.day} {local:%b %H:%M} IST"
    except (TypeError, ValueError):
        return None


def _day(v: Any) -> str:
    from datetime import date
    try:
        d = date.fromisoformat(str(v))
        return f"{d.day} {d:%b}"
    except (TypeError, ValueError):
        return "today"


def _verdicts(r: dict) -> str:
    return f"{_n(r.get('coins'), 'coin')} rated for {_day(r.get('date'))}; {_n(r.get('changed'), 'verdict')} changed."


def _reverify(r: dict) -> str:
    s = f"{_n(r.get('verified'), 'key')} OK"
    if r.get("permission_failed"):
        s += f", {_n(r['permission_failed'], 'key')} turned off (permissions)"
    if r.get("errors"):
        s += f", {_n(r['errors'], 'check')} couldn't reach the exchange"
    return s + "."


def _autopilot(r: dict) -> str:
    due = r.get("due")
    if due == 0:
        nxt = _when(r.get("next_due_at"))
        return "No plans were due." + (f" Next buy: {nxt}." if nxt else " No active plans.")
    s = f"{_n(r.get('bought'), 'plan')} bought"
    if r.get("failed"):
        s += f", {r['failed']:,} failed"
    if due is not None:
        s += f" (of {due:,} due)"
    return s + "."


def _crash(r: dict) -> str:
    dd = r.get("drawdown_pct")
    if r.get("level") is None:
        return f"BTC is {dd}% below its 30-day high; no crash level reached." if dd is not None else "No crash level reached."
    return f"BTC is {dd}% below its 30-day high (level {r['level']}%); {_n(r.get('alerts'), 'alert')} sent."


def _radar(r: dict) -> str:
    return f"{_n(r.get('new_listings'), 'new listing')}, {_n(r.get('trending'), 'trending coin')} checked."


FORMATTERS: dict[str, Callable[[dict], str]] = {
    "verdicts_daily": _verdicts,
    "exchange_reverify": _reverify,
    "verdict_scoring": lambda r: (f"Scored {_n(r.get('scored_7d'), 'verdict')} at 7 days and {_n(r.get('scored_30d'), 'verdict')} at 30 days."
                                  + (f" {_n(r.get('skipped'), 'verdict')} had no price yet." if r.get("skipped") else "")),
    "autopilot_buys": _autopilot,
    "paper_snapshot": lambda r: f"{_n(r.get('snapshots'), 'Paper Money account')} valued.",
    "crash_coach": _crash,
    "radar_scan": _radar,
    "radar_digest": lambda r: f"Digest sent to {_n(r.get('sent'), 'member')}.",
    "news_fetch": lambda r: f"{_n(r.get('added'), 'new story', 'new stories')} summarised.",
    "events_alerts": lambda r: (f"{_n(r.get('sent'), 'alert')} sent for {_n(r.get('events'), 'event')} tomorrow."
                                if r.get("events") else "No events tomorrow."),
}

_STATUS = {"off": "Skipped: this feature is switched off (Admin › Features).",
           "no data": "Skipped: price data wasn't available."}


def _pairs(r: dict) -> str:
    parts = []
    for k, v in r.items():
        if isinstance(v, (dict, list)):
            v = f"{len(v)} items"
        parts.append(f"{str(k).replace('_', ' ')}: {v}")
    return ", ".join(parts)[:200] or "Done."


def describe(name: str, result: Any, error: Optional[str] = None) -> str:
    if error:
        return f"Failed: {error}"
    if result is None:
        return "Done."
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return str(result)[:200]
    if result.get("status") in _STATUS and len(result) == 1:
        return _STATUS[result["status"]]
    fmt = FORMATTERS.get(name)
    if fmt:
        try:
            return fmt(result)
        except Exception:  # noqa: BLE001 — a formatter bug must never break the admin screen
            pass
    return _pairs(result)
