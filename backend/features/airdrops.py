"""Airdrop Finder (₹2,000 plan and up): the team's weekly list of live airdrops, each run through
Coin X-Ray, with the steps to join and a per-user checklist.

airdrops {_id, name, coin, chain, status live|ended, reward, deadline, link, description,
          steps: [{id, text}], xray: {label, score}, created_at, updated_at}
airdrop_progress {_id: "<uid>:<airdrop_id>", user_id, airdrop_id, done_steps: [step ids]}
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

import plans
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

router = APIRouter(tags=["airdrops"])


class StepIn(BaseModel):
    done: bool = True


class StepDef(BaseModel):
    id: Optional[str] = Field(None, max_length=20)
    text: str = Field(..., min_length=1, max_length=300)


class AirdropIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    coin: Optional[str] = Field(None, max_length=15)
    chain: Optional[str] = Field(None, max_length=30)
    status: str = Field("live", pattern="^(live|ended)$")
    reward: Optional[str] = Field(None, max_length=120)
    deadline: Optional[str] = Field(None, max_length=10)          # YYYY-MM-DD (or empty)

    @field_validator("deadline")
    @classmethod
    def _date(cls, v):
        if v in (None, ""):
            return None
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError:
            raise ValueError("Deadline must be a real date (YYYY-MM-DD).")
    link: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = Field(None, max_length=800)
    steps: list[StepDef] = Field(default_factory=list, max_length=30)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def reconcile_steps(incoming: list[StepDef], old: list[dict]) -> list[dict]:
    """Give every step a stable id so members' ticks follow the step, not its position.

    1. An id the client sends is kept (the admin editor sends back the id of every step it loaded; a create may
       carry ids too). Only the first use of an id in one save counts; repeats are treated as id-less.
    2. A step without an id reuses the id of an old step with the same text that no other step claimed (covers a
       client that sends text only, e.g. a reordered paste).
    3. Anything else is a new step with a fresh id that never collides with an old or claimed id.
    QA 3 Nov: ids used to be assigned by position, so reordering moved every member's ticks."""
    old_ids = {s["id"] for s in old if s.get("id")}
    claimed: set[str] = {s.id for s in incoming if s.id}
    by_text: dict[str, list[str]] = {}
    for s in old:
        if s.get("id") and s["id"] not in claimed:
            by_text.setdefault(_norm(s.get("text", "")), []).append(s["id"])
    out, used = [], set()
    for s in incoming:
        sid = s.id if s.id and s.id not in used else None
        if sid is None:
            pool = by_text.get(_norm(s.text)) or []
            while pool and sid is None:
                cand = pool.pop(0)
                if cand not in used:
                    sid = cand
        if sid is None:
            sid = uuid.uuid4().hex[:8]
            while sid in used or sid in old_ids or sid in claimed:
                sid = uuid.uuid4().hex[:8]
        used.add(sid)
        out.append({"id": sid, "text": s.text.strip()})
    return out


def public(a: dict, done: Optional[list] = None) -> dict:
    return {"id": a["_id"], "name": a["name"], "coin": a.get("coin"), "chain": a.get("chain"), "status": a.get("status", "live"),
            "reward": a.get("reward"), "deadline": a.get("deadline"), "link": a.get("link"),
            "description": a.get("description"), "steps": a.get("steps") or [],
            "xray": a.get("xray"),
            **({"done_steps": [i for i in done if i in {st["id"] for st in a.get("steps") or []}]} if done is not None else {}),
            "updated_at": iso(a.get("updated_at"))}


@router.get("/airdrops")
async def listing(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "airdrops")
    uid = str(user["_id"])
    prog = {p["airdrop_id"]: p.get("done_steps", []) async for p in db().airdrop_progress.find({"user_id": uid})}
    rows = [a async for a in db().airdrops.find({}).sort([("status", -1), ("deadline", 1)])]
    rows.sort(key=lambda a: (a.get("status") != "live", a.get("deadline") or "9999"))
    return {"items": [public(a, prog.get(a["_id"], [])) for a in rows]}


@router.post("/airdrops/{airdrop_id}/steps/{step_id}")
async def tick(airdrop_id: str, step_id: str, body: StepIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "airdrops")
    a = await db().airdrops.find_one({"_id": airdrop_id})
    if not a or step_id not in {s["id"] for s in a.get("steps") or []}:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Step not found."})
    uid = str(user["_id"])
    op = "$addToSet" if body.done else "$pull"
    await db().airdrop_progress.update_one({"_id": f"{uid}:{airdrop_id}"},
                                           {op: {"done_steps": step_id}, "$set": {"user_id": uid, "airdrop_id": airdrop_id}},
                                           upsert=True)
    await events.track(db(), "airdrop_step", user_id=uid, props={"airdrop": airdrop_id})
    p = await db().airdrop_progress.find_one({"_id": f"{uid}:{airdrop_id}"})
    return public(a, p.get("done_steps", []))


# ---------------------------------------------------------------- admin helpers ----
async def save(body: AirdropIn, airdrop_id: Optional[str] = None) -> dict:
    from features.xray import run_xray
    now = utcnow()
    existing = await db().airdrops.find_one({"_id": airdrop_id}) if airdrop_id else None
    if airdrop_id and not existing:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Airdrop not found."})
    steps = reconcile_steps(body.steps, (existing or {}).get("steps") or [])
    doc = {**body.model_dump(exclude={"steps"}), "steps": steps, "updated_at": now}
    if doc.get("coin"):
        doc["coin"] = doc["coin"].upper()
    # Check the coin AND the link; show the riskier answer (a real coin behind a fake claim page is still a scam).
    checks = []
    for target in (doc.get("coin"), doc.get("link")):
        if target:
            try:
                x = await run_xray(target)
                checks.append({"label": x["label"], "score": x["score"]})
            except Exception:  # noqa: BLE001 — an unreachable data source shouldn't block saving
                pass
    doc["xray"] = max(checks, key=lambda c: c["score"]) if checks else None
    if airdrop_id:
        res = await db().airdrops.update_one({"_id": airdrop_id}, {"$set": doc})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Airdrop not found."})
        # Ticks on steps the admin removed are dropped, so a later step can't inherit them.
        await db().airdrop_progress.update_many({"airdrop_id": airdrop_id},
                                                {"$pull": {"done_steps": {"$nin": [st["id"] for st in steps]}}})
        return public(await db().airdrops.find_one({"_id": airdrop_id}))
    doc.update(_id=uuid.uuid4().hex[:12], created_at=now)
    await db().airdrops.insert_one(doc)
    return public(doc)
