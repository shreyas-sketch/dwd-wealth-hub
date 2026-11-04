"""Job registry.

Each job: name → (label, schedule, coroutine fn(ctx)). Schedules are IST:
  ("daily", hour, minute) · ("weekly", weekday, hour, minute) · ("every", minutes)
Every run writes `job_runs` {_id, name, at, ok, result|error, ms}.
"""
from __future__ import annotations

import importlib
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from growth.clock import IST, as_utc, utcnow

log = logging.getLogger("jobs")

# name → (label, schedule, "module:function")
JOBS: dict[str, tuple[str, tuple, str]] = {
    "verdicts_daily": ("Daily AI verdicts (top 10 coins)", ("daily", 5, 30), "features.verdicts:job_daily"),
    "exchange_reverify": ("Re-check linked exchange keys", ("daily", 5, 40), "features.autopilot:job_reverify"),
    "autopilot_buys": ("SIP Autopilot buys", ("daily", 10, 0), "features.autopilot:job_buys"),
    "paper_snapshot": ("Paper Money daily values", ("daily", 23, 50), "features.paper:job_snapshot"),
    "crash_coach": ("Crash Coach check", ("every", 60), "features.ask:job_crash"),
    "radar_scan": ("Early Coin Radar scan", ("every", 60), "features.radar:job_scan"),
    "radar_digest": ("Early Coin Radar daily digest", ("daily", 9, 0), "features.radar:job_digest"),
    "news_fetch": ("News Decoder fetch + summaries", ("every", 120), "features.news:job_fetch"),
    "events_alerts": ("Events Calendar day-before alerts", ("daily", 18, 0), "features.calendar:job_alerts"),
}


@dataclass
class Ctx:
    db: object
    now: datetime


def schedule_text(s: tuple) -> str:
    if s[0] == "daily":
        return f"Daily {s[1]:02d}:{s[2]:02d} IST"
    if s[0] == "weekly":
        return f"{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][s[1]]} {s[2]:02d}:{s[3]:02d} IST"
    return f"Every {s[1]} min"


def _fn(path: str):
    mod, name = path.split(":")
    return getattr(importlib.import_module(mod), name)


async def run(db, name: str, now: Optional[datetime] = None) -> dict:
    if name not in JOBS:
        raise KeyError(name)
    now = now or utcnow()
    t0 = time.time()
    row = {"_id": uuid.uuid4().hex, "name": name, "at": now}
    try:
        result = await _fn(JOBS[name][2])(Ctx(db, now))
        row.update(ok=True, result=result)
    except Exception as e:  # noqa: BLE001
        log.exception("job %s failed", name)
        row.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
    row["ms"] = int((time.time() - t0) * 1000)
    try:
        await db.job_runs.insert_one(row)
    except Exception:  # noqa: BLE001
        log.warning("job_runs insert failed", exc_info=True)
    return row


def _last_slot(s: tuple, now: datetime) -> datetime:
    local = as_utc(now).astimezone(IST)
    if s[0] == "daily":
        slot = local.replace(hour=s[1], minute=s[2], second=0, microsecond=0)
        if slot > local:
            slot -= timedelta(days=1)
        return slot
    if s[0] == "weekly":
        slot = local.replace(hour=s[2], minute=s[3], second=0, microsecond=0) - timedelta(days=(local.weekday() - s[1]) % 7)
        if slot > local:
            slot -= timedelta(days=7)
        return slot
    return local - timedelta(minutes=s[1])


async def due(db, now: Optional[datetime] = None) -> list[str]:
    now = now or utcnow()
    out = []
    for name, (_, sched, _) in JOBS.items():
        last = await db.job_runs.find_one({"name": name}, sort=[("at", -1)])
        slot = _last_slot(sched, now)
        if not last or as_utc(last["at"]) < slot.astimezone(as_utc(now).tzinfo):
            out.append(name)
    return out


WORKER_ID = uuid.uuid4().hex[:12]
LOCK_MINUTES = 30


async def claim_lock(db, name: str, now: Optional[datetime] = None, minutes: int = LOCK_MINUTES,
                     owner: Optional[str] = None) -> bool:
    """Lease lock in Mongo so that with several web workers (or a cron tick) each due job runs once.
    Upsert on a filter that only matches a free/expired lock: if another worker holds it, the insert
    hits the duplicate _id and we skip. A crashed holder's lease simply expires."""
    from pymongo.errors import DuplicateKeyError
    now = now or utcnow()
    try:
        await db.job_locks.find_one_and_update(
            {"_id": name, "until": {"$lt": now}},
            {"$set": {"until": now + timedelta(minutes=minutes), "by": owner or WORKER_ID, "at": now}}, upsert=True)
        return True
    except DuplicateKeyError:
        return False


async def release_lock(db, name: str, owner: Optional[str] = None) -> None:
    await db.job_locks.update_one({"_id": name, "by": owner or WORKER_ID},
                                  {"$set": {"until": datetime(2000, 1, 1, tzinfo=as_utc(utcnow()).tzinfo)}})


async def _claim(db, name: str, now: datetime) -> bool:
    return await claim_lock(db, name, now)


async def _release(db, name: str) -> None:
    await release_lock(db, name)


async def tick(db, now: Optional[datetime] = None) -> dict:
    ran = {}
    for name in await due(db, now):
        if not await _claim(db, name, now or utcnow()):
            continue
        try:
            if name not in await due(db, now):          # another worker finished it a moment ago
                continue
            r = await run(db, name, now)
            ran[name] = r.get("ok")
        finally:
            await _release(db, name)
    return ran


def start_scheduler(db):
    """In-process scheduler: checks every minute which jobs are due."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sch = AsyncIOScheduler(timezone="UTC")
    sch.add_job(tick, "interval", minutes=1, args=[db], id="tick", max_instances=1, coalesce=True)
    sch.start()
    return sch


async def listing(db) -> list[dict]:
    from util import iso
    out = []
    for name, (label, sched, _) in JOBS.items():
        last = await db.job_runs.find_one({"name": name}, sort=[("at", -1)])
        out.append({"name": name, "label": label, "schedule": schedule_text(sched),
                    "last": run_view(name, last) if last else None})
    return out


def run_view(name: str, row: dict) -> dict:
    """One job_runs row as the admin sees it: a sentence (`summary`) plus the raw result for the details view."""
    from util import iso
    from .summaries import describe
    return {"at": iso(row.get("at")), "ok": row.get("ok"), "summary": describe(name, row.get("result"), row.get("error")),
            "result": row.get("result") or row.get("error"), "ms": row.get("ms")}
