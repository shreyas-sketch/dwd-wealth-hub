"""Ask Deepak AI (₹5,000 plan): answers from the team's own recorded sessions, plus the Goal Tracker
and Crash Coach.

kb_docs   {_id, title, words, chunks, uploaded_at}
kb_chunks {_id, doc_id, title, i, text, tokens: [str]}
ask_threads {_id, user_id, title, messages: [{role, text, sources?, at}], updated_at}
crash_notes {_id: "notes", notes: [{level, note}]}
crash_state {_id: "btc", active, level, drawdown_pct, at, note}

Retrieval is a plain BM25 over chunk tokens (no embeddings vendor). The model answers only from the
retrieved chunks, in a mentor's plain voice, and refuses personal "should I buy X" calls.
"""
from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import appsettings
import llm
import market
import plans
from core.deps import user_dep
from core.flags import is_on
from growth import events
from growth.clock import as_utc, utcnow
from notify.service import alert
from state import db
from util import iso

router = APIRouter(prefix="/ask", tags=["ask"])

STOP = set("""a an the and or but if then so to of in on at for from by with without is are was were be been being it its this
that these those i you he she we they me my your our their them his her what which who whom how when where why can could
should would will just do does did not no yes as about into than too very also there here have has had get got""".split())
TOKEN = re.compile(r"[a-z0-9]+")
VTT_TS = re.compile(r"^\[?\d{1,2}:\d{2}(:\d{2})?(\.\d+)?\]?\s*(-->.*)?$")
CHUNK_WORDS = 350
ADVICE = re.compile(r"\b(should i (buy|sell|invest)|is it (a )?good time to buy|which coin (should|to) buy|"
                    r"tell me (a|which) coin|will .{1,20} (go up|pump|reach)|price target|how much will)\b", re.I)


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


def clean_transcript(raw: str) -> str:
    """Strip WEBVTT headers, cue numbers and timecodes; keep the words."""
    out = []
    lines = raw.replace("\r", "").split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.upper().startswith("WEBVTT") or "-->" in s or VTT_TS.match(s):
            continue
        if s.isdigit() and i + 1 < len(lines) and "-->" in lines[i + 1]:
            continue
        s = re.sub(r"^\[\d{1,2}:\d{2}(:\d{2})?\]\s*", "", s)
        out.append(s)
    return " ".join(out)


def chunk(text: str, n: int = CHUNK_WORDS) -> list[str]:
    words = text.split()
    step = int(n * 0.85)
    return [" ".join(words[i:i + n]) for i in range(0, max(1, len(words)), step) if words[i:i + n]]


async def ingest(d, title: str, raw: str) -> dict:
    text = clean_transcript(raw)
    parts = chunk(text)
    doc_id = uuid.uuid4().hex[:12]
    now = utcnow()
    rows = [{"_id": f"{doc_id}:{i}", "doc_id": doc_id, "title": title, "i": i, "text": t, "tokens": tokens(t)}
            for i, t in enumerate(parts)]
    if rows:
        await d.kb_chunks.insert_many(rows)
    doc = {"_id": doc_id, "title": title, "words": len(text.split()), "chunks": len(rows), "uploaded_at": now}
    await d.kb_docs.insert_one(doc)
    reset_kb_cache()
    return {"id": doc_id, "title": title, "chunks": len(rows), "words": doc["words"], "uploaded_at": iso(now)}


_KB: dict = {"sig": None, "checked": 0.0, "rows": [], "tf": [], "lens": [], "avg": 1.0, "post": {}}


async def _kb_index(d) -> dict:
    """In-memory BM25 index of the knowledge base, one per worker. Rebuilt only when the KB changes
    (checked at most every 30 s). Load test (3 Nov): with Deepak's real transcripts (~1,800 chunks) the old
    per-question scan read up to 3–4 MB from Mongo and scored every chunk in Python (~120 ms of CPU per
    question); this answers from memory in a few ms."""
    import time
    now = time.time()
    if _KB["sig"] is not None and now - _KB["checked"] < 30:
        return _KB
    last = await d.kb_docs.find_one({}, sort=[("uploaded_at", -1)], projection={"uploaded_at": 1})
    sig = (await d.kb_docs.count_documents({}), await d.kb_chunks.count_documents({}),
           str((last or {}).get("uploaded_at")))
    _KB["checked"] = now
    if sig == _KB["sig"]:
        return _KB
    rows, tfs, lens, post = [], [], [], {}
    async for r in d.kb_chunks.find({}, {"tokens": 1, "text": 1, "title": 1}):
        i = len(rows)
        tf = Counter(r.get("tokens") or [])
        rows.append({"_id": r["_id"], "title": r.get("title"), "text": r.get("text", "")})
        tfs.append(tf)
        lens.append(sum(tf.values()))
        for t in tf:
            post.setdefault(t, []).append(i)
    _KB.update(sig=sig, rows=rows, tf=tfs, lens=lens, post=post, avg=(sum(lens) / len(lens)) if lens else 1.0)
    return _KB


async def search(d, query: str, k: int = 5) -> list[dict]:
    q = tokens(query)
    if not q:
        return []
    kb = await _kb_index(d)
    n = len(kb["rows"]) or 1
    scores: dict[int, float] = {}
    for t in set(q):
        docs = kb["post"].get(t)
        if not docs:
            continue
        idf = math.log(1 + (n - len(docs) + 0.5) / (len(docs) + 0.5))
        for i in docs:
            f = kb["tf"][i][t]
            scores[i] = scores.get(i, 0.0) + idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * kb["lens"][i] / kb["avg"]))
    best = sorted(scores.items(), key=lambda x: -x[1])[:k]
    return [kb["rows"][i] for i, sc in best if sc > 0]


def reset_kb_cache() -> None:
    _KB.update(sig=None, checked=0.0)


class AskIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    thread_id: Optional[str] = Field(None, max_length=40)


SYSTEM = ("You are Ask Deepak, the study assistant for a crypto education program for Indian learners. "
          "Answer like a patient mentor: plain English, short paragraphs, concrete steps, numbers in rupees where it helps. "
          "Use ONLY the session notes given; if they don't cover the question, say so and give the safe general principle. "
          "Never tell this person which coin to buy or sell, never give price predictions or targets, never promise returns. "
          "For 'should I buy X' questions, explain how to judge it themselves (Coin X-Ray, Verdicts, position size, their plan). "
          "Remind about safety where relevant: never share a seed phrase, use trade-only API keys.")


def _snippet(t: str, n: int = 220) -> str:
    return t[:n].rsplit(" ", 1)[0] + "…" if len(t) > n else t


def fake_answer(question: str, hits: list[dict], refused: bool) -> dict:
    if refused:
        return {"answer": ("I won't tell you which coin to buy — that has to be your call. Here's how to judge it: run it "
                           "through Coin X-Ray for red flags, check today's Verdict, and only put in an amount that fits "
                           "your plan's allocation. If a 50% fall would hurt, the amount is too big."), "refused": True}
    if not hits:
        return {"answer": ("Our sessions don't cover that exactly. The safe principle: start small, buy regularly instead "
                           "of all at once, keep coins on trusted exchanges or your own wallet, and never share your seed phrase."),
                "refused": False}
    first = hits[0]["text"]
    return {"answer": f"From the session \"{hits[0]['title']}\": {_snippet(first, 420)}\n\nIn short: take it step by step, "
                      "and keep the amount small until you're confident.", "refused": False}


async def _answer(question: str, history: list[dict], strict: bool) -> dict:
    refused = bool(ADVICE.search(question))
    hits = await search(db(), question, 5)
    notes = "\n\n".join(f"[{h['title']}] {h['text']}" for h in hits)
    convo = "\n".join(f"{m['role']}: {m['text'][:400]}" for m in history[-6:])
    prompt = (f"Earlier in this chat:\n{convo or '(none)'}\n\nSession notes:\n{notes or '(no matching notes)'}\n\n"
              f"Question: {question}\n\nReturn {{\"answer\": str, \"refused\": bool}} — refused=true only if you declined "
              "to name a coin to buy/sell or predict a price.")
    try:
        out = await llm.complete_json(task="ask", system=SYSTEM, prompt=prompt, model="strong", max_tokens=4000,
                                      fake=lambda: fake_answer(question, hits, refused))
    except llm.LLMError:
        if strict:
            raise
        out = fake_answer(question, hits, refused)
    return {"answer": out.get("answer") or "", "refused": bool(out.get("refused")) or refused,
            "sources": [{"title": h["title"], "snippet": _snippet(h["text"])} for h in hits[:3]]}


async def answer(question: str, history: list[dict]) -> dict:
    """A first question in a new chat depends only on the question and the KB, so identical questions share one
    AI answer for ASK_CACHE_SECONDS (default 1 h). In a webinar, hundreds type the same question Deepak just
    showed on screen; this turns hundreds of AI calls into one. Fallback answers (AI busy) are never cached."""
    if history:
        return await _answer(question, history, strict=False)
    import copy
    import os

    import market
    key = "ask:" + " ".join(tokens(question))[:300] + ("" if not ADVICE.search(question) else ":advice")
    try:
        return copy.deepcopy(await market._cached(key, int(os.environ.get("ASK_CACHE_SECONDS", "3600") or 3600),
                                                  lambda: _answer(question, [], strict=True)))
    except llm.LLMError:
        return await _answer(question, [], strict=False)


@router.post("")
async def ask(body: AskIn, user: dict = Depends(user_dep())):
    plan = await plans.require(db(), user, "ask")
    if not is_on("ASK"):
        raise HTTPException(status_code=503, detail={"code": "off", "msg": "Ask Deepak is paused right now."})
    uid = str(user["_id"])
    th = None
    if body.thread_id:
        th = await db().ask_threads.find_one({"_id": body.thread_id, "user_id": uid})
    usage = await plans.consume(db(), user, "ask", plan)
    out = await answer(body.question.strip(), (th or {}).get("messages", []))
    now = utcnow()
    msgs = [{"role": "user", "text": body.question.strip(), "at": now},
            {"role": "assistant", "text": out["answer"], "sources": out["sources"], "at": now}]
    if th:
        await db().ask_threads.update_one({"_id": th["_id"]}, {"$push": {"messages": {"$each": msgs}}, "$set": {"updated_at": now}})
        tid = th["_id"]
    else:
        tid = uuid.uuid4().hex[:16]
        await db().ask_threads.insert_one({"_id": tid, "user_id": uid, "title": body.question.strip()[:60],
                                           "messages": msgs, "created_at": now, "updated_at": now})
    await events.track(db(), "ask_asked", user_id=uid)
    return {"thread_id": tid, "answer": out["answer"], "sources": out["sources"], "refused": out["refused"], "usage": usage}


@router.get("/threads")
async def threads(user: dict = Depends(user_dep())):
    rows = db().ask_threads.find({"user_id": str(user["_id"])}, {"title": 1, "updated_at": 1}).sort("updated_at", -1).limit(40)
    return {"items": [{"id": r["_id"], "title": r["title"], "updated_at": iso(r["updated_at"])} async for r in rows]}


@router.get("/threads/{thread_id}")
async def thread(thread_id: str, user: dict = Depends(user_dep())):
    th = await db().ask_threads.find_one({"_id": thread_id, "user_id": str(user["_id"])})
    if not th:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Chat not found."})
    return {"id": th["_id"], "messages": [{**{k: v for k, v in m.items() if k != "at"}, "at": iso(m.get("at"))}
                                          for m in th.get("messages", [])]}


# ------------------------------------------------------------------ coach ----
async def goal_for(user: dict) -> Optional[dict]:
    p = await db().crypto_plans.find_one({"user_id": str(user["_id"])}, sort=[("created_at", 1)])
    if not p:
        return None
    from features.plan import _context, shape
    rates, portfolio, paper = await _context(user)
    s = await shape(user, p, rates, portfolio, paper)
    gp = s["goal_progress"]
    return {"name": p["goal_name"], "target_inr": p["target_inr"], "value_inr": gp["value_inr"], "pct": gp["pct"],
            "source": gp["source"]}


@router.get("/coach")
async def coach(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "ask")
    st = await db().crash_state.find_one({"_id": "btc"})
    crash = None
    if st and st.get("active"):
        crash = {"active": True, "level": st["level"], "drawdown_pct": st["drawdown_pct"], "note": st.get("note"),
                 "at": iso(st.get("at"))}
    return {"goal": await goal_for(user), "crash": crash}


DEFAULT_NOTES = {
    20: "BTC is down 20% from its recent high. This is normal in crypto — it has happened many times in good years. "
        "Don't sell in panic. If you have a monthly plan, keep it running; that's what it's for.",
    30: "BTC is down 30%. Falls like this test everyone. Check your plan: are you still investing only money you won't "
        "need for years? If yes, stay the course. If you're losing sleep, your amount is too big — reduce new buys, don't panic-sell.",
    40: "BTC is down 40%. Past cycles had falls of 50–80% before recovering — and some coins never recovered. Stick to "
        "Bitcoin/Ethereum-heavy plans, keep buying small amounts only if your plan says so, and avoid leverage completely.",
}


async def notes_map(d) -> dict[int, str]:
    doc = await d.crash_notes.find_one({"_id": "notes"})
    out = dict(DEFAULT_NOTES)
    for n in (doc or {}).get("notes", []):
        out[int(n["level"])] = n["note"]
    return out


async def job_crash(ctx) -> dict:
    if not is_on("CRASH_COACH"):
        return {"status": "off"}
    d = ctx.db
    hist = await market.history("BTC", 31)
    price = await market.price("BTC")
    if not hist or not price:
        return {"status": "no data"}
    high = max(max(p for _, p in hist), price)
    dd = round((1 - price / high) * 100, 1)
    levels = sorted((await appsettings.get(d))["crash_levels"])
    hit = max([lv for lv in levels if dd >= lv], default=None)
    notes = await notes_map(d)
    if hit is None:
        await d.crash_state.update_one({"_id": "btc"}, {"$set": {"active": False, "drawdown_pct": dd, "checked_at": ctx.now}},
                                       upsert=True)
        return {"drawdown_pct": dd, "level": None}
    note = notes.get(hit) or DEFAULT_NOTES.get(hit) or (
        f"BTC is down {hit}% or more from its recent high. Falls like this are common in crypto. Don't sell in panic; "
        "check your plan and keep any monthly buys only if you won't need the money for years.")
    prev = await d.crash_state.find_one({"_id": "btc"})
    await d.crash_state.update_one({"_id": "btc"}, {"$set": {"active": True, "level": hit, "drawdown_pct": dd, "note": note,
                                                             "at": ctx.now, "checked_at": ctx.now}}, upsert=True)
    sent = 0
    recent = prev and prev.get("active") and prev.get("level") == hit and prev.get("at") and \
        (ctx.now - as_utc(prev["at"])).days < 7
    if not recent:
        week = ctx.now.strftime("%G-W%V")
        from notify.service import alert_many       # bulk: one plan lookup for everyone, inbox in batches
        sent = await alert_many(d, await plans.users_with(d, "ask", ctx.now), "crash",
                                f"Crash Coach: BTC is down {dd:.0f}% from its 30-day high", note, link="/app/ask",
                                dedupe=f"crash:{hit}:{week}")
    return {"drawdown_pct": dd, "level": hit, "alerts": sent}
