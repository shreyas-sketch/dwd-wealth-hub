"""News Decoder (₹5,000 plan): crypto news in plain English with "what it means for you", tagged by
coin, plus a "real or hype?" check on any pasted link or text.

news {_id: hash(url), title, source, url, published_at, coins, summary, what_it_means, sentiment, fetched_at}
Feeds (RSS, live): CoinDesk, Cointelegraph, Decrypt. # NEEDS: confirm feed URLs once with network.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime
import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import llm
import plans
from core.deps import user_dep
from core.flags import is_on
from core.vendors import vendor_mode
from features.calendar import user_coins
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

router = APIRouter(prefix="/news", tags=["news"])
FEEDS = [("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
         ("Cointelegraph", "https://cointelegraph.com/rss"),
         ("Decrypt", "https://decrypt.co/feed")]
COIN_WORDS = {"BTC": ["bitcoin", "btc"], "ETH": ["ethereum", "ether", "eth"], "SOL": ["solana", "sol"],
              "XRP": ["xrp", "ripple"], "BNB": ["bnb", "binance coin"], "DOGE": ["dogecoin", "doge"],
              "ADA": ["cardano", "ada"], "TRX": ["tron", "trx"], "LINK": ["chainlink"], "AVAX": ["avalanche", "avax"],
              "TON": ["toncoin", "ton"], "SUI": ["sui"], "PEPE": ["pepe"], "SHIB": ["shiba"], "LTC": ["litecoin"],
              "DOT": ["polkadot"], "USDT": ["tether", "usdt"]}
KEEP_DAYS = 10


def tag_coins(text: str) -> list[str]:
    t = " " + re.sub(r"[^a-z0-9 ]", " ", text.lower()) + " "
    return [sym for sym, words in COIN_WORDS.items() if any(f" {w} " in t for w in words)]


def _fake_items(now) -> list[dict]:
    base = [
        ("Bitcoin ETFs see steady inflows as institutions add exposure", "BTC", "positive"),
        ("Ethereum developers set date for next network upgrade", "ETH", "neutral"),
        ("Solana meme-coin frenzy cools as trading volumes drop", "SOL", "negative"),
        ("Regulators abroad tighten rules on crypto exchanges' customer funds", None, "neutral"),
        ("XRP climbs after payments partnership announcement", "XRP", "positive"),
        ("Large token unlock ahead for a mid-cap coin; analysts expect selling pressure", None, "negative"),
    ]
    out = []
    for i, (title, coin, sent) in enumerate(base):
        out.append({"title": title, "source": ["CoinDesk", "Cointelegraph", "Decrypt"][i % 3],
                    "url": f"https://example.com/sample-news-{i + 1}", "published_at": now - timedelta(hours=2 + i * 5),
                    "coins": [coin] if coin else [], "sentiment": sent, "raw": title})
    return out


def _fake_summary(title: str, sentiment: str) -> dict:
    return {"summary": f"Sample summary (QA mode): {title}.",
            "what_it_means": {"positive": "Good news can lift prices short term, but it's often already priced in. Don't chase.",
                              "negative": "Bad news can drag prices for a while. If you hold for years, one headline rarely changes the plan.",
                              "neutral": "Mostly background. Nothing to do unless it changes why you hold the coin."}[sentiment],
            "sentiment": sentiment}


def parse_rss(source: str, content: bytes) -> list[dict]:
    out = []
    root = ET.fromstring(content)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:600]
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate") or "")
        except Exception:  # noqa: BLE001
            pub = utcnow()
        if title and link:
            out.append({"title": title, "source": source, "url": link, "published_at": pub,
                        "coins": tag_coins(title + " " + desc), "raw": f"{title}. {desc}"})
    return out


async def _fetch_rss() -> list[dict]:
    out = []
    async with httpx.AsyncClient(timeout=15, headers={"user-agent": "Mozilla/5.0"}, follow_redirects=True) as c:
        for source, url in FEEDS:
            try:
                r = await c.get(url)
                out.extend(parse_rss(source, r.content))
            except Exception:  # noqa: BLE001
                continue
    return out


async def job_fetch(ctx) -> dict:
    if not is_on("NEWS"):
        return {"status": "off"}
    d, now = ctx.db, ctx.now
    mode = vendor_mode("news")
    if mode == "off":
        return {"status": "off"}
    items = _fake_items(now) if mode == "fake" else await _fetch_rss()
    added = 0
    for it in items[:40]:
        _id = hashlib.sha1(it["url"].encode()).hexdigest()[:20]
        if await d.news.find_one({"_id": _id}, {"_id": 1}):
            continue
        sent = it.get("sentiment") or "neutral"
        sys = ("Explain one crypto news item to an Indian beginner. `summary`: one or two plain sentences. "
               "`what_it_means`: one or two sentences on what it means for a long-term small investor — no buy/sell "
               "instructions, no price predictions. `sentiment`: positive|negative|neutral for crypto prices.")
        try:
            ai = await llm.complete_json(task="news", system=sys, prompt=f"News: {it['raw'][:900]}\nReturn "
                                         '{"summary", "what_it_means", "sentiment"}.',
                                         fake=lambda: _fake_summary(it["title"], sent))
        except llm.LLMError:
            continue
        # upsert, not insert: two workers (or the QA seed and the job) may fetch the same item at once
        await d.news.update_one({"_id": _id}, {"$setOnInsert": {"title": it["title"], "source": it["source"], "url": it["url"],
                                 "published_at": it["published_at"], "coins": it["coins"],
                                 "summary": ai.get("summary"), "what_it_means": ai.get("what_it_means"),
                                 "sentiment": ai.get("sentiment") if ai.get("sentiment") in ("positive", "negative", "neutral") else "neutral",
                                 "fetched_at": now}}, upsert=True)
        added += 1
    await d.news.delete_many({"published_at": {"$lt": now - timedelta(days=KEEP_DAYS)}})
    return {"added": added}


@router.get("")
async def news(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "news")
    mine = await user_coins(db(), user)
    rows = [n async for n in db().news.find({}).sort("published_at", -1).limit(50)]
    await events.track(db(), "news_viewed", user_id=str(user["_id"]))
    return {"items": [{"id": n["_id"], "title": n["title"], "source": n["source"], "url": n["url"],
                       "published_at": iso(n["published_at"]), "coins": n.get("coins") or [], "summary": n.get("summary"),
                       "what_it_means": n.get("what_it_means"), "sentiment": n.get("sentiment", "neutral"),
                       "yours": bool(set(n.get("coins") or []) & mine)} for n in rows]}


class CheckIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=4000)


HYPE = re.compile(r"100x|1000x|guarantee|to the moon|next bitcoin|don.t miss|last chance|explode|skyrocket|insider|"
                  r"secret|presale|only today|millionaire|will (hit|reach|touch) \$?[\d,.]+|by next (week|month)|"
                  r"price prediction|guaranteed", re.I)


def _fake_check(text: str) -> dict:
    hits = sorted({m.group(0).lower() for m in HYPE.finditer(text)})
    if hits:
        return {"verdict": "hype", "reasons": [f"Uses hype words: {', '.join(hits[:4])}",
                                               "No named source or verifiable numbers"],
                "summary": "This reads like promotion, not news. Treat any coin it pushes with extra suspicion."}
    if re.search(r"https?://(www\.)?(coindesk|cointelegraph|decrypt|reuters|bloomberg|economictimes|livemint)\.", text, re.I):
        return {"verdict": "real", "reasons": ["From an established news outlet"],
                "summary": "Looks like a normal news report. Still read past the headline before acting."}
    return {"verdict": "unclear", "reasons": ["Not enough to judge — no source we recognise"],
            "summary": "Check whether a known news site reports the same thing before believing it."}


@router.post("/check")
async def check(body: CheckIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "news")
    sys = ("Judge whether a piece of crypto news or a promo is real news or hype, for an Indian beginner. "
           "Look for named sources, verifiable facts, hype words, urgency and coin-shilling. Plain English.")
    try:
        out = await llm.complete_json(task="news_check", system=sys,
                                      prompt=f"Text or link:\n{body.text[:3000]}\nReturn "
                                      '{"verdict": "real|hype|unclear", "reasons": [str], "summary": str}.',
                                      fake=lambda: _fake_check(body.text))
    except llm.LLMError:
        out = _fake_check(body.text)
    if out.get("verdict") not in ("real", "hype", "unclear"):
        out["verdict"] = "unclear"
    await events.track(db(), "news_checked", user_id=str(user["_id"]))
    return {"verdict": out["verdict"], "reasons": out.get("reasons") or [], "summary": out.get("summary") or ""}
