"""Admin panel API (role admin). Everything under /api/admin."""
from __future__ import annotations

import asyncio
import csv
import io
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import appsettings
import market
import plans
from auth import public_user
from core import flags
from core.deps import admin_dep
from core.vendors import REQUIRED_KEYS, vendor_mode
from features import airdrops as airdrops_f
from features import ask as ask_f
from features import baskets as baskets_f
from features import calendar as calendar_f
from features import verdicts as verdicts_f
from growth import events
from growth.clock import IST, as_utc, utcnow
from jobs import registry
from state import db
from util import iso, oid

router = APIRouter(prefix="/admin", tags=["admin"])
Admin = Depends(admin_dep())

FEATURE_EVENTS = {"whatif_run": "What If", "xray_run": "Coin X-Ray", "verdicts_viewed": "Crypto Verdicts",
                  "forecast_run": "Forecast", "debate_run": "Debate", "plan_saved": "My Crypto Plan",
                  "paper_started": "Paper Money", "paper_trade": "Paper trades", "airdrop_step": "Airdrop Finder",
                  "dca_plan_saved": "SIP Autopilot", "chart_read": "Chart Reader", "ask_asked": "Ask Deepak AI",
                  "basket_practice": "Baskets (practice)", "basket_invest": "Baskets (real)", "radar_viewed": "Coin Radar",
                  "calendar_viewed": "Events Calendar", "p2p_viewed": "P2P Rates", "news_viewed": "News Decoder",
                  "news_checked": "Real or hype"}


def ist_day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=IST).astimezone(timezone.utc)


async def paid_users(d, now: Optional[datetime] = None) -> dict[str, str]:
    """user_id → best paid plan (live subscription; same statuses as plans.effective_plan)."""
    now = now or utcnow()
    out: dict[str, str] = {}
    async for s in d.subscriptions.find({"status": {"$in": ["active", "authenticated", "pending"]},
                                         "current_end": {"$gt": now}}, {"user_id": 1, "plan": 1}):
        if s.get("plan") in plans.PLANS and plans.RANK[s["plan"]] > plans.RANK[out.get(s["user_id"], "free")]:
            out[s["user_id"]] = s["plan"]
    return out


async def nonfree_plans(d, now: Optional[datetime] = None) -> dict[str, str]:
    return await plans.nonfree_plans(d, now)


# ------------------------------------------------------------------ pulse ----
async def _admin_ids(d) -> list:
    return [u["_id"] async for u in d.users.find({"role": "admin"}, {"_id": 1})]


async def _granted(d, now: datetime) -> dict[str, str]:
    """user_id → best live admin-granted plan."""
    out: dict[str, str] = {}
    async for g in d.plan_grants.find({"ends_at": {"$gt": now}}, {"user_id": 1, "plan": 1}):
        if g.get("plan") in plans.PLANS and plans.RANK[g["plan"]] > plans.RANK[out.get(g["user_id"], "free")]:
            out[g["user_id"]] = g["plan"]
    return out


@router.get("/pulse")
async def pulse(_: dict = Admin):
    d = db()
    now = utcnow()
    today = now.astimezone(IST).date()
    members = {"role": {"$ne": "admin"}, "phone": {"$exists": True}}
    admin_ids = {str(x) for x in await _admin_ids(d)}
    total = await d.users.count_documents(members)
    t0 = ist_day_start(today)
    signups_today = await d.users.count_documents({**members, "created_at": {"$gte": t0}})
    signups_7d = await d.users.count_documents({**members, "created_at": {"$gte": t0 - timedelta(days=6)}})
    paid = {u: p for u, p in (await paid_users(d, now)).items() if u not in admin_ids}
    granted = {u: p for u, p in (await _granted(d, now)).items() if u not in admin_ids and u not in paid}
    # trial = on a live trial and neither paying nor granted; counted in Mongo, not in a Python loop
    skip = [o for o in (oid(u) for u in list(paid) + list(granted)) if o]
    trial = await d.users.count_documents({**members, "trial_ends_at": {"$gt": now}, "_id": {"$nin": skip}})
    lite = sum(1 for p in paid.values() if p == "lite")
    pro = sum(1 for p in paid.values() if p == "pro")
    g_lite = sum(1 for p in granted.values() if p == "lite")
    g_pro = sum(1 for p in granted.values() if p == "pro")
    counts: dict[str, int] = {}                  # signups per IST day: one indexed read of 14 days of created_at
    async for u in d.users.find({**members, "created_at": {"$gte": t0 - timedelta(days=13)}}, {"_id": 0, "created_at": 1}):
        k = as_utc(u["created_at"]).astimezone(IST).date().isoformat()
        counts[k] = counts.get(k, 0) + 1
    by_day = [{"date": (today - timedelta(days=i)).isoformat(), "count": counts.get((today - timedelta(days=i)).isoformat(), 0)}
              for i in range(13, -1, -1)]
    src: dict[str, int] = {}
    async for r in d.users.aggregate([{"$match": members}, {"$group": {"_id": "$acquisition.source", "n": {"$sum": 1}}}]):
        k = r["_id"] or "unknown"
        src[k] = src.get(k, 0) + r["n"]
    usage: dict[str, int] = {}                   # one index-only count per event name, run together (~40 ms on 180k events)
    since = now - timedelta(days=7)
    names = list(FEATURE_EVENTS)
    counts_7d = await asyncio.gather(*[d.events.count_documents({"name": n, "ts": {"$gte": since}}) for n in names])
    for name, n in zip(names, counts_7d):
        if n:
            usage[FEATURE_EVENTS[name]] = usage.get(FEATURE_EVENTS[name], 0) + n
    return {"kpis": {"users_total": total, "signups_today": signups_today, "signups_7d": signups_7d,
                     "trial_active": trial, "lite_active": lite, "pro_active": pro,
                     "granted_active": g_lite + g_pro,
                     "mrr_inr": lite * plans.PRICES_INR["lite"] + pro * plans.PRICES_INR["pro"],
                     "paid_conversion_pct": round((lite + pro) / total * 100, 1) if total else 0.0},
            "signups_by_day": by_day,
            "by_source": sorted([{"source": k, "count": v} for k, v in src.items()], key=lambda x: -x["count"]),
            "feature_usage_7d": sorted([{"feature": k, "count": v} for k, v in usage.items()], key=lambda x: -x["count"]),
            "plan_mix": [{"plan": "pro", "count": pro + g_pro}, {"plan": "lite", "count": lite + g_lite},
                         {"plan": "trial", "count": trial},
                         {"plan": "free", "count": max(0, total - pro - lite - g_pro - g_lite - trial)}]}


# ------------------------------------------------------------------ webinar ----
def _window(start: str, end: str) -> tuple[datetime, datetime]:
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "bad_date", "msg": "Dates must be YYYY-MM-DD."})
    if e < s:
        s, e = e, s
    if (e - s).days > 92:
        raise HTTPException(status_code=400, detail={"code": "range_too_long", "msg": "Pick at most 3 months."})
    return ist_day_start(s), ist_day_start(e + timedelta(days=1))


def _not_paying(paid: dict, granted: dict, uid: str) -> bool:
    return uid not in paid and uid not in granted


@router.get("/webinar")
async def webinar(start: str, end: str, _: dict = Admin):
    d = db()
    a, b = _window(start, end)
    now = utcnow()
    admin_ids = await _admin_ids(d)
    admin_set = {str(x) for x in admin_ids}
    ids = {str(u["_id"]) async for u in d.users.find(
        {"created_at": {"$gte": a, "$lt": b}, "role": {"$ne": "admin"}, "status": {"$ne": "revoked"}}, {"_id": 1})}
    logins = 0
    async for r in d.events.aggregate([
            {"$match": {"name": {"$in": ["login", "signup"]}, "ts": {"$gte": a, "$lt": b},
                        "user_id": {"$nin": [None, *admin_set]}}},
            {"$group": {"_id": "$user_id"}}, {"$count": "n"}]):
        logins = r["n"]
    feat: dict[str, dict] = {}                   # one pass over the window: uses per tool, distinct people per tool
    async for r in d.events.aggregate([
            {"$match": {"name": {"$in": list(FEATURE_EVENTS)}, "ts": {"$gte": a, "$lt": b}}},
            {"$project": {"_id": 0, "name": 1, "who": {"$ifNull": ["$user_id", "$anon_id"]}}},
            {"$match": {"who": {"$nin": [None, *admin_set]}}},
            {"$group": {"_id": {"n": "$name", "w": "$who"}, "uses": {"$sum": 1}}},
            {"$group": {"_id": "$_id.n", "users": {"$sum": 1}, "uses": {"$sum": "$uses"}}}], allowDiskUse=True):
        label = FEATURE_EVENTS[r["_id"]]
        f = feat.setdefault(label, {"users": 0, "uses": 0})
        f["users"] += r["users"]
        f["uses"] += r["uses"]
    paid = await paid_users(d, now)
    granted = await _granted(d, now)
    bought = {"lite": sum(1 for u in ids if paid.get(u) == "lite"), "pro": sum(1 for u in ids if paid.get(u) == "pro")}
    return {"signups": len(ids), "logins": logins,
            "feature_usage": sorted([{"feature": k, "users": v["users"], "uses": v["uses"]} for k, v in feat.items()],
                                    key=lambda x: -x["users"]),
            "bought": bought, "day3_list_count": sum(1 for u in ids if _not_paying(paid, granted, u))}


@router.get("/webinar/day3.csv")
async def day3_csv(start: str, end: str, _: dict = Admin):
    d = db()
    a, b = _window(start, end)
    now = utcnow()
    paid = await paid_users(d, now)
    granted = await _granted(d, now)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "phone", "signed_up_ist", "source", "tools_used", "last_login_ist"])
    rows = [u async for u in d.users.find({"created_at": {"$gte": a, "$lt": b}, "role": {"$ne": "admin"},
                                           "status": {"$ne": "revoked"}},
                                          {"name": 1, "phone": 1, "created_at": 1, "acquisition.source": 1,
                                           "last_login_at": 1}).sort("created_at", 1)
            if _not_paying(paid, granted, str(u["_id"]))]
    used_by: dict[str, int] = {}                 # one grouped query instead of one count per person
    ids = [str(u["_id"]) for u in rows]
    for k in range(0, len(ids), 5000):
        async for r in d.events.aggregate([
                {"$match": {"name": {"$in": list(FEATURE_EVENTS)}, "ts": {"$gte": a}, "user_id": {"$in": ids[k:k + 5000]}}},
                {"$project": {"_id": 0, "user_id": 1}},
                {"$group": {"_id": "$user_id", "n": {"$sum": 1}}}]):
            used_by[r["_id"]] = r["n"]
    for u in rows:
        uid = str(u["_id"])
        ll = u.get("last_login_at") or u.get("created_at")
        w.writerow([u.get("name") or "", u.get("phone") or "", as_utc(u["created_at"]).astimezone(IST).strftime("%Y-%m-%d %H:%M"),
                    (u.get("acquisition") or {}).get("source", ""), used_by.get(uid, 0),
                    as_utc(ll).astimezone(IST).strftime("%Y-%m-%d %H:%M") if ll else ""])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="day3-{start}-to-{end}.csv"'})


# ------------------------------------------------------------------ users ----
async def _row(d, u: dict) -> dict:
    ep = await plans.effective_plan(d, u)
    return {"id": str(u["_id"]), "phone": u.get("phone"), "name": u.get("name"), "email": u.get("email"),
            "role": u.get("role") or "user", "plan": ep["plan"], "plan_source": ep["source"],
            "source": (u.get("acquisition") or {}).get("source"), "created_at": iso(u.get("created_at")),
            "last_login_at": iso(u.get("last_login_at")), "trial_ends_at": ep["trial_ends_at"],
            "paid_until": ep["paid_until"], "status": u.get("status") or "active"}


@router.get("/users")
async def users(q: Optional[str] = None, plan: Optional[str] = None, page: int = Query(1, ge=1, le=10000),
                _: dict = Admin):
    d = db()
    flt: dict = {}
    if q:
        rx = {"$regex": re.escape(q.strip().lstrip("+").replace(" ", "")), "$options": "i"}
        flt = {"$or": [{"phone": rx}, {"name": {"$regex": re.escape(q.strip()), "$options": "i"}}, {"email": rx}]}
    size = 50
    if plan in plans.PLANS:                       # plan filter resolved in bulk, then paged in Mongo
        best = await nonfree_plans(d)
        if plan == "free":
            ids = [o for o in (oid(u) for u in best) if o]
            flt = {**flt, "_id": {"$nin": ids}}
        else:
            ids = [o for o in (oid(u) for u, p in best.items() if p == plan) if o]
            flt = {**flt, "_id": {"$in": ids}}
    total = await d.users.count_documents(flt)
    cur = d.users.find(flt).sort("created_at", -1).skip((page - 1) * size).limit(size)
    return {"total": total, "items": [await _row(d, u) async for u in cur]}


async def _user(user_id: str) -> dict:
    o = oid(user_id)
    u = await db().users.find_one({"_id": o}) if o else None
    if not u:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "User not found."})
    return u


@router.get("/users/{user_id}")
async def user_detail(user_id: str, _: dict = Admin):
    u = await _user(user_id)
    d = db()
    info = await plans.plan_info(d, u)
    evs = [{"name": e["name"], "ts": iso(e["ts"]), "props": e.get("props") or {}}
           async for e in d.events.find({"user_id": user_id}).sort("ts", -1).limit(60)]
    subs = [{"id": s["_id"], "plan": s["plan"], "status": s["status"], "current_end": iso(s.get("current_end")),
             "cancel_at_cycle_end": s.get("cancel_at_cycle_end")} async for s in d.subscriptions.find({"user_id": user_id})]
    grants = [{"plan": g["plan"], "ends_at": iso(g["ends_at"]), "by": g.get("by")} async for g in d.plan_grants.find({"user_id": user_id})]
    return {"user": {**public_user(u), "status": u.get("status") or "active",
                     "source": (u.get("acquisition") or {}).get("source"), "last_login_at": iso(u.get("last_login_at"))},
            "plan": info, "usage": info["limits"], "subscriptions": subs, "grants": grants, "events": evs}


class GrantIn(BaseModel):
    plan: str = Field(..., pattern="^(free|lite|pro)$")
    months: int = Field(1, ge=0, le=36)


@router.post("/users/{user_id}/grant")
async def grant(user_id: str, body: GrantIn, admin: dict = Admin):
    await _user(user_id)
    now = utcnow()
    await db().plan_grants.update_many({"user_id": user_id, "ends_at": {"$gt": now}}, {"$set": {"ends_at": now}})
    if body.plan != "free" and body.months > 0:
        await db().plan_grants.insert_one({"user_id": user_id, "plan": body.plan, "ends_at": now + timedelta(days=31 * body.months),
                                           "by": str(admin["_id"]), "at": now})
    await events.track(db(), "plan_granted", user_id=user_id, props={"plan": body.plan, "months": body.months})
    return await user_detail(user_id, admin)


class TrialIn(BaseModel):
    days: int = Field(..., ge=0, le=60)


@router.post("/users/{user_id}/trial")
async def trial(user_id: str, body: TrialIn, admin: dict = Admin):
    u = await _user(user_id)
    await db().users.update_one({"_id": u["_id"]}, {"$set": {"trial_ends_at": utcnow() + timedelta(days=body.days)}})
    await events.track(db(), "trial_extended", user_id=user_id, props={"days": body.days})
    return await user_detail(user_id, admin)


class StatusIn(BaseModel):
    status: str = Field(..., pattern="^(active|revoked)$")


@router.post("/users/{user_id}/status")
async def set_status(user_id: str, body: StatusIn, admin: dict = Admin):
    u = await _user(user_id)
    if str(u["_id"]) == str(admin["_id"]):
        raise HTTPException(status_code=400, detail={"code": "self", "msg": "You can't change your own status."})
    await db().users.update_one({"_id": u["_id"]}, {"$set": {"status": body.status}})
    return await user_detail(user_id, admin)


# ------------------------------------------------------------------ control ----
@router.get("/flags")
async def get_flags(_: dict = Admin):
    await flags.refresh(db(), force=True)
    return {"items": flags.listing()}


class FlagIn(BaseModel):
    key: str
    on: Optional[bool] = None


@router.post("/flags")
async def set_flag(body: FlagIn, admin: dict = Admin):
    try:
        await flags.set_flag(db(), body.key, body.on, by=str(admin.get("phone") or admin.get("email") or admin["_id"]))
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "unknown_flag", "msg": "Unknown switch."})
    await events.track(db(), "feature_toggled", user_id=str(admin["_id"]), props={"key": body.key, "on": body.on})
    return {"items": flags.listing()}


@router.get("/settings")
async def get_settings(_: dict = Admin):
    return await appsettings.get(db())


@router.get("/settings/spec")
async def settings_spec(_: dict = Admin):
    """Limits for each setting, so the admin form checks exactly what the server checks."""
    return appsettings.spec()


@router.post("/settings")
async def set_settings(body: dict, _: dict = Admin):
    return await appsettings.update(db(), body)


@router.get("/vendors")
async def vendors(_: dict = Admin):
    out = []
    for n in REQUIRED_KEYS:
        try:
            m = vendor_mode(n)
        except Exception as e:  # noqa: BLE001
            m = f"error: {e}"
        out.append({"name": n, "mode": m})
    import llm
    return {"vendors": out, "ai_pools": llm.pool_stats()}


@router.get("/jobs")
async def jobs(_: dict = Admin):
    return {"items": await registry.listing(db())}


@router.post("/jobs/{name}/run")
async def run_job(name: str, _: dict = Admin):
    if name not in registry.JOBS:
        raise HTTPException(status_code=404, detail={"code": "unknown_job", "msg": "Unknown job."})
    r = await registry.run(db(), name)
    view = registry.run_view(name, r)
    return {"ok": view["ok"], "summary": view["summary"], "result": view["result"], "ms": view["ms"], "at": view["at"]}


# ------------------------------------------------------------------ content: airdrops ----
@router.get("/airdrops")
async def list_airdrops(_: dict = Admin):
    return {"items": [airdrops_f.public(a) async for a in db().airdrops.find({}).sort("created_at", -1)]}


@router.post("/airdrops")
async def create_airdrop(body: airdrops_f.AirdropIn, _: dict = Admin):
    return await airdrops_f.save(body)


@router.put("/airdrops/{airdrop_id}")
async def update_airdrop(airdrop_id: str, body: airdrops_f.AirdropIn, _: dict = Admin):
    return await airdrops_f.save(body, airdrop_id)


@router.delete("/airdrops/{airdrop_id}")
async def delete_airdrop(airdrop_id: str, _: dict = Admin):
    await db().airdrops.delete_one({"_id": airdrop_id})
    await db().airdrop_progress.delete_many({"airdrop_id": airdrop_id})
    return {"ok": True}


# ------------------------------------------------------------------ content: baskets ----
@router.get("/baskets")
async def list_baskets(_: dict = Admin):
    return {"items": [baskets_f.public(b) async for b in db().baskets.find({}).sort("created_at", 1)]}


@router.post("/baskets")
async def create_basket(body: baskets_f.BasketIn, _: dict = Admin):
    return await baskets_f.save(body)


@router.put("/baskets/{basket_id}")
async def update_basket(basket_id: str, body: baskets_f.BasketIn, _: dict = Admin):
    return await baskets_f.save(body, basket_id)


@router.delete("/baskets/{basket_id}")
async def delete_basket(basket_id: str, _: dict = Admin):
    """Soft delete: Autopilot basket plans stop on their next run with a clear message."""
    await db().baskets.update_one({"_id": basket_id}, {"$set": {"active": False}})
    return {"ok": True}


# ------------------------------------------------------------------ content: events ----
@router.get("/events")
async def list_events(_: dict = Admin):
    return {"items": [{**calendar_f.public(e, set()), "source": e.get("source")}
                      async for e in db().crypto_events.find({}).sort("date", 1)]}


@router.post("/events")
async def create_event(body: calendar_f.EventIn, _: dict = Admin):
    return await calendar_f.save(body)


@router.put("/events/{event_id}")
async def update_event(event_id: str, body: calendar_f.EventIn, _: dict = Admin):
    return await calendar_f.save(body, event_id)


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, _: dict = Admin):
    await db().crypto_events.delete_one({"_id": event_id})
    return {"ok": True}


# ------------------------------------------------------------------ Monday picks ----
class PickIn(BaseModel):
    symbol: str = Field(..., max_length=15)
    reasoning: str = Field(..., min_length=1, max_length=800)


class PicksIn(BaseModel):
    week_of: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    published: bool = False
    picks: list[PickIn] = Field(default_factory=list, max_length=5)


@router.get("/picks")
async def get_picks(_: dict = Admin):
    p = await db().picks.find_one({}, sort=[("_id", -1)])
    if not p:
        return {"week_of": verdicts_f.week_of(), "published": False, "picks": []}
    return {"week_of": p["_id"], "published": p.get("published", False), "picks": p.get("picks", [])}


@router.get("/picks/suggest")
async def suggest(_: dict = Admin):
    return {"picks": await verdicts_f.suggest_picks(db())}


@router.post("/picks")
async def save_picks(body: PicksIn, _: dict = Admin):
    wk = body.week_of or verdicts_f.week_of()
    syms = [p.symbol.upper() for p in body.picks]
    px = await market.prices(syms) if syms else {}
    out = []
    for p in body.picks:
        s = p.symbol.upper()
        v = await db().verdicts.find_one({"symbol": s}, sort=[("date", -1)])
        info = px.get(s) or await market.search(s)
        if not info:
            raise HTTPException(status_code=400, detail={"code": "not_found", "msg": f"Unknown coin {s}."})
        out.append({"symbol": s, "name": info.get("name"), "verdict": (v or {}).get("verdict"),
                    "confidence": (v or {}).get("confidence"), "reasoning": p.reasoning.strip(),
                    "price_at_pick_usd": info.get("price_usd")})
    await db().picks.replace_one({"_id": wk}, {"_id": wk, "published": body.published, "picks": out, "updated_at": utcnow()},
                                 upsert=True)
    return {"week_of": wk, "published": body.published, "picks": out}


# ------------------------------------------------------------------ crash notes ----
class NoteIn(BaseModel):
    level: int = Field(..., ge=5, le=90)
    note: str = Field(..., min_length=1, max_length=800)


class NotesIn(BaseModel):
    notes: list[NoteIn]


@router.get("/crash-notes")
async def get_notes(_: dict = Admin):
    m = await ask_f.notes_map(db())
    levels = (await appsettings.get(db()))["crash_levels"]
    return {"notes": [{"level": lv, "note": m.get(lv, "")} for lv in sorted(set(levels) | set(m))]}


@router.post("/crash-notes")
async def set_notes(body: NotesIn, _: dict = Admin):
    await db().crash_notes.replace_one({"_id": "notes"}, {"_id": "notes", "notes": [n.model_dump() for n in body.notes]},
                                       upsert=True)
    return await get_notes(_)


# ------------------------------------------------------------------ knowledge base ----
@router.get("/kb")
async def kb(_: dict = Admin):
    return {"items": [{"id": k["_id"], "title": k["title"], "chunks": k["chunks"], "words": k["words"],
                       "uploaded_at": iso(k["uploaded_at"])} async for k in db().kb_docs.find({}).sort("uploaded_at", -1)]}


@router.post("/kb")
async def kb_upload(file: UploadFile = File(...), title: Optional[str] = Form(None), _: dict = Admin):
    name = (file.filename or "").lower()
    if not name.endswith((".txt", ".vtt", ".md", ".srt")):
        raise HTTPException(status_code=400, detail={"code": "bad_type", "msg": "Upload a .txt, .vtt, .srt or .md file."})
    raw = await file.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail={"code": "too_large", "msg": "Files up to 8 MB."})
    text = raw.decode("utf-8", errors="ignore")
    out = await ask_f.ingest(db(), (title or file.filename or "Session").strip()[:120], text)
    if not out["chunks"]:
        raise HTTPException(status_code=400, detail={"code": "empty", "msg": "No text found in that file."})
    return out


@router.delete("/kb/{doc_id}")
async def kb_delete(doc_id: str, _: dict = Admin):
    await db().kb_docs.delete_one({"_id": doc_id})
    await db().kb_chunks.delete_many({"doc_id": doc_id})
    ask_f.reset_kb_cache()
    return {"ok": True}


# ------------------------------------------------------------------ ETF flows ----
class EtfIn(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    net_usd_m: float = Field(..., ge=-100000, le=100000)
    note: Optional[str] = Field(None, max_length=200)


@router.get("/etf-flows")
async def etf(_: dict = Admin):
    return {"items": [{"date": e["date"], "net_usd_m": e["net_usd_m"], "note": e.get("note")}
                      async for e in db().etf_flows.find({}).sort("date", -1).limit(60)]}


@router.post("/etf-flows")
async def etf_save(body: EtfIn, _: dict = Admin):
    await db().etf_flows.replace_one({"_id": body.date}, {"_id": body.date, **body.model_dump()}, upsert=True)
    return await etf(_)
