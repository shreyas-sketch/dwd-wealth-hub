"""Coin X-Ray (with Scam Check inside): one box takes a coin name, a contract address, a link
or a pasted message, and answers safe / risky / likely scam with the red flags.

POST /api/xray {query}        anonymous: settings.anon_xray_per_day a day; members: plan limit
GET  /api/xray/history

Rules decide the score and the flags (explainable, testable); the AI only writes the one-line
headline and "what the coin does" in plain English.
"""
from __future__ import annotations

import os

import ipaddress
import re
from datetime import date
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import appsettings
import llm
import market
import plans
from auth import optional_user
from core.deps import user_dep
from core.vendors import vendor_mode
from features import DISCLAIMER
from growth import events
from growth.clock import utcnow
from state import db
from util import iso, smart_round

router = APIRouter(tags=["xray"])

LEGIT_DOMAINS = {"kucoin.com", "binance.com", "coindcx.com", "wazirx.com", "mudrex.com", "coinbase.com",
                 "phantom.app", "metamask.io", "coingecko.com", "coinmarketcap.com", "delta.exchange",
                 "etherscan.io", "solscan.io", "bscscan.com", "jup.ag", "raydium.io", "uniswap.org",
                 "zebpay.com", "giottus.com", "bitbns.com", "okx.com", "bybit.com", "tradingview.com",
                 "opensea.io", "pancakeswap.finance", "trustwallet.com"}
BRANDS = {"kucoin", "binance", "coindcx", "wazirx", "mudrex", "coinbase", "phantom", "metamask", "trustwallet",
          "zebpay", "okx", "bybit", "uniswap", "pancakeswap", "opensea"}
BRAND_NAMES = {"kucoin": "KuCoin", "binance": "Binance", "coindcx": "CoinDCX", "wazirx": "WazirX", "mudrex": "Mudrex",
               "coinbase": "Coinbase", "phantom": "Phantom", "metamask": "MetaMask", "trustwallet": "Trust Wallet",
               "zebpay": "ZebPay", "okx": "OKX", "bybit": "Bybit", "uniswap": "Uniswap", "pancakeswap": "PancakeSwap",
               "opensea": "OpenSea"}
_LOOK = str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "7": "t", "!": "i", "|": "l"})


def _edits(a: str, b: str) -> int:
    """Edit distance where swapping two neighbouring letters counts as one edit (short strings only)."""
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def lookalike_brand(host: str) -> Optional[str]:
    """'blnance.com', 'kuc0in.io', 'metamsk.app' → the brand being copied (1–2 letters off, or digits for letters)."""
    # Each dot label whole ("bin-ance") and each hyphen part on its own ("blnance-bonus" → "blnance"). A hyphen part
    # must be within one letter of the brand, and real English words near a brand name are skipped, so
    # "finance-news.com" or "balance-check.com" aren't called fakes.
    parts = []
    for label in host.split("."):
        parts.append((label.replace("-", ""), None))
        parts.extend((p, 1) for p in label.split("-") if p and "-" in label)
    for label, max_edits in parts:
        if label in COMMON_WORDS:
            continue
        lab = label.translate(_LOOK).replace("rn", "m").replace("vv", "w")
        if len(lab) < 4:
            continue
        for b in BRANDS:
            allowed = max_edits if max_edits is not None else (1 if len(b) < 7 else 2)
            if lab == b or (len(b) >= 5 and abs(len(lab) - len(b)) <= 2 and _edits(lab, b) <= allowed):
                return b
    return None


COMMON_WORDS = {"finance", "balance", "advance", "romance", "nuance", "insurance", "binary", "kitchen", "okay",
                "metal", "meta", "trust", "coins", "phantom", "ledger", "bitcoin", "crypto", "exchange", "market"}
ODD_TLDS = {"xyz", "top", "click", "live", "site", "online", "shop", "icu", "buzz", "cc", "vip", "club", "work",
            "loan", "win", "bid", "rest", "gq", "tk", "ml", "cf"}
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "cutt.ly", "rb.gy", "is.gd", "t.me", "wa.me", "chat.whatsapp.com"}
LINK_WORDS = ("airdrop", "claim", "giveaway", "double", "bonus", "reward", "connect-wallet", "walletconnect",
              "verify", "validate", "support", "recover", "unlock", "kyc", "free-crypto", "doubler", "profit",
              "earn", "mining", "payout", "withdraw", "wallet-sync", "presale", "restore", "seed-phrase", "rectify")
# Bump when the X-Ray rules change, so saved results (the radar) are checked again under the new rules.
XRAY_RULES_VERSION = 3

URL_RE = re.compile(r"(https?://[^\s]+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?)", re.I)
EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

MSG_RULES: list[tuple[str, str, str, str]] = [   # (regex, severity, title, detail)
    (r"guarantee|assured|fixed (daily |monthly |weekly )?(return|profit|income)|risk[- ]?free",
     "high", "Promises guaranteed returns", "Nobody can guarantee crypto returns. This is the most common scam line."),
    (r"\b\d{1,3}\s?% (daily|per day|a day|weekly|per week|monthly|per month)",
     "high", "Promises a fixed % every day/week/month", "Fixed high returns are how Ponzi schemes pull people in."),
    (r"double your|2x your|triple your|10x (in|within)", "high", "Promises to multiply your money",
     "Real investments don't promise to double money on a timetable."),
    (r"(send|deposit|transfer|pay)\b.{0,30}\b(usdt|crypto|btc|eth|bitcoin|money|amount|fee)|wallet address",
     "high", "Asks you to send money or crypto first", "Scammers ask for a deposit or a 'fee' before you can withdraw."),
    (r"(fee|tax|charge).{0,30}(withdraw|unlock|release)", "high", "Asks for a fee to withdraw",
     "A real platform never asks for an extra payment to release your own money."),
    (r"seed phrase|recovery phrase|secret phrase|private key|12 words|24 words", "high",
     "Mentions your seed phrase or private key", "Never share or type your seed phrase anywhere. Anyone with it can take everything."),
    (r"(customer|technical) support|support team|binance team|kucoin team|account (will be )?(blocked|suspended|frozen)|kyc (update|pending|expired)",
     "high", "Pretends to be the exchange or support", "Exchanges don't message you first on WhatsApp/Telegram about blocks or KYC."),
    (r"part[- ]?time|task|like and earn|prepaid|rating job|review job|work from home",
     "high", "Looks like a 'task' job scam", "Task scams pay small amounts first, then ask you to 'invest' to unlock bigger tasks."),
    (r"(sebi|rbi).{0,20}(approved|registered|guarantee)", "high", "Claims SEBI/RBI approval for crypto",
     "Crypto schemes in India are not SEBI or RBI approved. This claim is false."),
    (r"only today|last chance|limited (slots|seats|time)|hurry|within \d+ ?(hours|hrs|minutes)|ends tonight",
     "medium", "Rushes you", "Pressure to act fast stops you from checking. Real chances don't vanish in hours."),
    (r"telegram|vip group|signal group|whatsapp group|join (our|my|the) group|premium group",
     "medium", "Pulls you into a private group", "Pump-and-dump and fake-signal groups run on Telegram and WhatsApp."),
    (r"100x|1000x|next (bitcoin|shiba|pepe)|to the moon|moon ?shot|gem alert|pump", "medium",
     "Hype words", "Hype like '100x' or 'next Bitcoin' is used to sell tokens to late buyers."),
    (r"(dm|message|contact) me|inbox me|call me", "low", "Asks you to contact them privately",
     "Moving the chat private keeps others from warning you."),
]


class XRayIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


def classify(q: str) -> str:
    s = q.strip()
    if EVM_RE.match(s) or (SOL_RE.match(s) and any(ch.isdigit() for ch in s) and len(s) >= 32):
        return "coin"
    if " " not in s and URL_RE.fullmatch(s) and "." in s and not re.fullmatch(r"[A-Za-z]{2,10}", s):
        return "link"
    if len(s.split()) >= 4 or len(s) > 40:
        return "message"
    return "coin"


def _flag(title: str, detail: str, severity: str, decisive: bool = False) -> dict:
    """decisive: on its own this means likely scam (e.g. a site posing as a real exchange), whatever else is seen."""
    f = {"title": title, "detail": detail, "severity": severity}
    if decisive:
        f["decisive"] = True
    return f


# Coins whose price runs on hype and memes rather than use. CoinGecko's categories catch most ("Meme", "Dog-Themed",
# "Frog-Themed" …); this list covers the big ones when categories aren't available.
MEME_SYMBOLS = {"DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "TRUMP", "BRETT", "POPCAT", "MOG", "BOME", "NEIRO",
                "MEW", "TURBO", "PNUT", "GOAT", "FARTCOIN", "SPX", "MOODENG", "DOGS", "BABYDOGE", "PENGU"}


def is_meme(c: dict) -> bool:
    cats = " ".join(str(x) for x in (c.get("categories") or [])).lower()
    return "meme" in cats or (str(c.get("symbol") or "").upper() in MEME_SYMBOLS)


UNKNOWN_SITE = "Not a crypto site we know"


def link_flags(url: str) -> tuple[list[dict], list[str]]:
    red, green = [], []
    u = url if "://" in url else "https://" + url
    p = urlparse(u)
    host = (p.hostname or "").lower().rstrip(".")
    path = (p.path or "") + "?" + (p.query or "")
    if url.lower().startswith("http://"):
        red.append(_flag("Not a secure (https) link", "Login or wallet pages without https are unsafe.", "medium"))
    try:
        ipaddress.ip_address(host)
        red.append(_flag("Link is a bare IP address", "Real exchanges use their own domain name, not a number.", "high"))
    except ValueError:
        pass
    if "xn--" in host:
        red.append(_flag("Disguised letters in the address", "This uses look-alike characters to copy a real site's name.", "high", decisive=True))
    root = ".".join(host.split(".")[-2:]) if host.count(".") >= 1 else host
    legit = any(host == d or host.endswith("." + d) for d in LEGIT_DOMAINS)
    if legit:
        green.append(f"Official domain ({root})")
    else:
        hit = [b for b in BRANDS if b in host.replace("-", "").replace(".", "")]
        if hit:
            red.append(_flag(f"Copies the name '{hit[0]}' but isn't the real site",
                             f"The real {BRAND_NAMES.get(hit[0], hit[0].title())} site is not {host}. "
                             "Look-alike sites steal logins and wallets.", "high", decisive=True))
        elif lookalike_brand(host):
            b = lookalike_brand(host)
            red.append(_flag(f"Spelled almost like '{b}' but isn't the real site",
                             f"{host} swaps or drops a letter to look like {BRAND_NAMES.get(b, b.title())}. "
                             "Look-alike sites steal logins and wallets.", "high", decisive=True))
        elif host and not any(f["severity"] == "high" for f in red):
            red.append(_flag(UNKNOWN_SITE,
                             "We only recognise the main exchanges, wallets and price sites. Check who runs this site "
                             "before you log in, pay or connect a wallet.", "low"))
    tld = host.rsplit(".", 1)[-1] if "." in host else ""
    if tld in ODD_TLDS and not legit:
        red.append(_flag(f"Unusual ending (.{tld})", "Cheap domain endings like this are common for short-lived scam sites.", "medium"))
    if host in SHORTENERS or root in SHORTENERS:
        red.append(_flag("Short link or chat invite", "You can't see where this leads; group invites are where pump schemes run.", "medium"))
    words = [w for w in LINK_WORDS if w in (host + path).lower()]
    if words and not legit:
        red.append(_flag(f"Bait words in the link ({', '.join(words[:3])})",
                         "'Claim', 'airdrop', 'verify wallet' links are the usual way wallets get drained.", "high"))
    return red, green


def message_flags(text: str) -> tuple[list[dict], list[str]]:
    red, green = [], []
    t = text.lower()
    for rx, sev, title, detail in MSG_RULES:
        try:
            if re.search(rx, t):
                red.append(_flag(title, detail, sev))
        except re.error:
            continue
    for m in URL_RE.findall(text):
        if "." in m and not re.fullmatch(r"\d+(\.\d+)+", m):
            r, _ = link_flags(m)
            for f in r:
                f["title"] = f"Link: {f['title']}"
            red.extend(r)
    if not red:
        green.append("No common scam lines found")
    return red, green


async def goplus_flags(chain: Optional[str], contract: Optional[str]) -> list[dict]:
    if not contract:
        return []
    mode = vendor_mode("goplus")
    if mode == "off":
        return []
    if mode == "fake":
        from market.fake import _rng
        r = _rng("goplus", contract.lower())
        out = []
        if r.random() < 0.35:
            out.append(_flag("Contract can block selling (honeypot risk)", "Security scan says you may be able to buy but not sell.", "high"))
        if r.random() < 0.5:
            out.append(_flag("Creator can mint more tokens", "New tokens can be printed, which dilutes holders.", "medium"))
        top = r.randint(20, 90)
        if top > 50:
            out.append(_flag(f"Top 10 wallets hold {top}%", "A few holders can dump on everyone else.", "high"))
        return out
    chain_ids = {"ethereum": "1", "binance-smart-chain": "56", "bsc": "56", "base": "8453", "polygon-pos": "137",
                 "arbitrum-one": "42161"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if EVM_RE.match(contract):
                cid = chain_ids.get(chain or "ethereum", "1")
                r = await c.get(f"https://api.gopluslabs.io/api/v1/token_security/{cid}",
                                params={"contract_addresses": contract.lower()})
                d = ((r.json() or {}).get("result") or {}).get(contract.lower()) or {}
            else:
                r = await c.get("https://api.gopluslabs.io/api/v1/solana/token_security",
                                params={"contract_addresses": contract})
                d = ((r.json() or {}).get("result") or {}).get(contract) or {}
    except Exception:  # noqa: BLE001
        return []
    out = []
    if str(d.get("is_honeypot")) == "1" or str(d.get("cannot_sell_all")) == "1":
        out.append(_flag("Contract can block selling (honeypot)", "Security scan says you may not be able to sell.", "high"))
    if str(d.get("is_mintable")) == "1" or (isinstance(d.get("mintable"), dict) and d["mintable"].get("status") == "1"):
        out.append(_flag("Creator can mint more tokens", "New tokens can be printed, which dilutes holders.", "medium"))
    if str(d.get("owner_change_balance")) == "1":
        out.append(_flag("Owner can change balances", "The creator can edit wallets' balances.", "high"))
    for k in ("buy_tax", "sell_tax"):
        try:
            if float(d.get(k) or 0) > 0.1:
                out.append(_flag(f"High {k.replace('_', ' ')} ({float(d[k]) * 100:.0f}%)", "A big cut is taken on every trade.", "medium"))
        except (TypeError, ValueError):
            pass
    try:
        top = sum(float(h.get("percent") or 0) for h in (d.get("holders") or [])[:10]) * 100
        if top > 50:
            out.append(_flag(f"Top 10 wallets hold {top:.0f}%", "A few holders can dump on everyone else.", "high"))
    except (TypeError, ValueError):
        pass
    return out


def coin_query(q: str) -> str:
    """'$PEPE' → 'PEPE', 'pepe coin' → 'pepe', 'Shiba Inu token' → 'Shiba Inu'."""
    q = q.strip().lstrip("$#").strip()
    q2 = re.sub(r"\s+(coin|token|crypto)$", "", q, flags=re.I).strip()
    return q2 or q


async def coin_flags(q: str) -> tuple[list[dict], list[str], Optional[dict]]:
    red, green = [], []
    try:
        c = await market.search(coin_query(q))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=503, detail={"code": "data_unavailable", "msg": "Coin data isn't reachable right now. Try again."})
    if not c:
        red.append(_flag("Not found on major price trackers", "It may be fake, a typo, or too new to be tracked. Be very careful.", "high"))
        return red, green, None
    if c.get("unlisted") or not c.get("rank"):
        red.append(_flag("Not ranked by market size", "Unranked tokens are tiny or unverified — easy to manipulate.", "high"))
    rank = c.get("rank")
    if is_meme(c):
        red.append(_flag("Meme coin", "Its price runs on hype and social media, not on use. Meme coins often fall 80–90% "
                         "after a run, even big ones.", "medium"))
    if rank and rank <= 20:
        green.append(f"Top {rank} coin by market size")
    elif rank and rank <= 100:
        green.append(f"Ranked #{rank} by market size")
    mcap, vol = c.get("market_cap_usd") or 0, c.get("volume_24h_usd") or 0
    if mcap and mcap < 1_000_000:
        red.append(_flag("Very small (under $1 million)", "Tiny coins can be pumped and dumped by a few wallets.", "high"))
    elif mcap and mcap < 50_000_000:
        red.append(_flag("Small coin (under $50 million)", "Small coins swing hard and can go to near zero.", "medium"))
    if mcap and vol / mcap > 1.5:
        red.append(_flag("Trading far above its size", "Daily trading is bigger than the whole coin — typical of a pump.", "medium"))
    elif mcap and vol / mcap < 0.002:
        red.append(_flag("Very thin trading", "Few buyers means you may not be able to sell at a fair price.", "medium"))
    ch = c.get("change_24h")
    if ch is not None and ch > 50:
        red.append(_flag(f"Already up {ch:.0f}% in a day", "Buying after a big pump is how people buy the top.", "medium"))
    elif ch is not None and ch < -40:
        red.append(_flag(f"Down {abs(ch):.0f}% in a day", "A crash this size often means insiders are selling.", "high"))
    g = c.get("genesis_date")
    if g:
        try:
            age = (date.today() - date.fromisoformat(g[:10])).days
            c["age_days"] = age
            if age < 30:
                red.append(_flag(f"Brand new ({age} days old)", "Most new tokens lose most of their value in the first months.", "high"))
            elif age < 90:
                red.append(_flag(f"New coin ({age} days old)", "Less than 3 months of trading. Many new coins fall sharply after listing.", "medium"))
            elif age < 180:
                red.append(_flag(f"Young coin ({age} days old)", "No track record through a bad market yet.", "low"))
            elif age > 1500:
                green.append("Has survived more than one market cycle")
        except ValueError:
            pass
    sym = c.get("symbol")
    if sym:
        try:
            on_b = sym in await market.listings("binance")
            on_k = sym in await market.listings("kucoin")
            if on_b and on_k:
                green.append("Listed on both Binance and KuCoin")
            elif on_b or on_k:
                green.append(f"Listed on {'Binance' if on_b else 'KuCoin'}")
        except Exception:  # noqa: BLE001
            pass
    red.extend(await goplus_flags(c.get("chain"), c.get("contract")))
    return red, green, c


def score_of(red: list[dict], green: list[str], rank: Optional[int] = None) -> tuple[int, str]:
    w = {"high": 30, "medium": 15, "low": 5}
    s = 15 + sum(w[f["severity"]] for f in red) - 8 * len(green)
    if rank and rank <= 10:
        s = min(s, 25)
    elif any(f["title"].startswith(("Brand new", "New coin")) for f in red):
        s = max(s, 30)                     # a coin under 3 months old is never shown as "safe"
    if any(f["title"] == "Meme coin" for f in red):
        s = max(s, 35)                     # a meme coin is never "Looks safe", even in the top 10 (QA 10 Nov: Pepe)
    if any(f["title"] == UNKNOWN_SITE for f in red):
        s = max(s, 30)                     # a site we don't know is never "Looks safe" (QA 10 Nov)
    if any(f.get("decisive") for f in red):
        s = max(s, 75)                     # a site posing as a real exchange is a likely scam (QA: blnance.com)
    s = max(0, min(100, s))
    return s, ("safe" if s < 30 else "risky" if s < 60 else "likely_scam")


def _fake_headline(kind: str, label: str, red: list[dict], coin: Optional[dict]) -> dict:
    name = (coin or {}).get("name") or "This"
    if kind == "coin":
        head = {"safe": f"{name} is an established coin — still volatile, but not a scam signal.",
                "risky": f"{name} carries real risk: {red[0]['title'].lower() if red else 'small and volatile'}.",
                "likely_scam": f"Stay away: {red[0]['title'].lower() if red else 'too many warning signs'}."}[label]
    elif kind == "link":
        unknown = any(f["title"] == UNKNOWN_SITE for f in red) and not any(f["severity"] != "low" for f in red)
        head = {"safe": "This looks like an official site. Still type the address yourself instead of clicking.",
                "risky": ("We don't know this site. Don't log in, pay or connect a wallet until you've checked who runs it."
                          if unknown else "Be careful with this link — check the address letter by letter."),
                "likely_scam": "Don't open this link or connect a wallet to it."}[label]
    else:
        head = {"safe": "No common scam lines here — still never send money to someone you met online.",
                "risky": "This message has warning signs. Don't send money or click links in it.",
                "likely_scam": "This reads like a scam. Don't reply, don't pay, don't share codes."}[label]
    what = (coin or {}).get("description") or ("A small token with no clear product we could verify." if coin else None)
    return {"headline": head, "what_it_does": what}


async def run_xray(query: str) -> dict:
    q = query.strip()
    kind = classify(q)
    coin = None
    if kind == "link":
        red, green = link_flags(q)
    elif kind == "message":
        red, green = message_flags(q)
    else:
        red, green, coin = await coin_flags(q)
    score, label = score_of(red, green, (coin or {}).get("rank"))
    red.sort(key=lambda f: {"high": 0, "medium": 1, "low": 2}[f["severity"]])
    sys = ("You explain crypto risk to Indian beginners in plain, calm English. One short sentence for `headline` "
           "(the answer first). For coins, `what_it_does` in two plain sentences, no hype, no price prediction, "
           "no buy/sell advice.")
    prompt = (f"Kind: {kind}\nInput: {q[:600]}\nLabel decided by rules: {label} (risk {score}/100)\n"
              f"Red flags: {[f['title'] for f in red]}\nGood signs: {green}\n"
              f"Coin data: {({k: coin.get(k) for k in ('name', 'symbol', 'rank', 'market_cap_usd', 'description')} if coin else None)}\n"
              'Return {"headline": str, "what_it_does": str|null}.')
    try:
        ai = await llm.complete_json(task="xray", system=sys, prompt=prompt,
                                     fake=lambda: _fake_headline(kind, label, red, coin))
    except llm.LLMError:
        ai = _fake_headline(kind, label, red, coin)
    out = {"kind": kind, "query": q[:300], "label": label, "score": score, "headline": ai.get("headline"),
           "red_flags": red, "green_flags": green, "coin": None, "what_it_does": None, "verdict": None,
           "disclaimer": DISCLAIMER}
    if kind == "coin" and coin:
        out["coin"] = {"symbol": coin.get("symbol"), "name": coin.get("name"), "rank": coin.get("rank"),
                       "price_usd": smart_round(coin.get("price_usd")), "market_cap_usd": coin.get("market_cap_usd"),
                       "volume_24h_usd": coin.get("volume_24h_usd"), "change_24h": coin.get("change_24h"),
                       "age_days": coin.get("age_days"), "chain": coin.get("chain"), "contract": coin.get("contract")}
        out["what_it_does"] = ai.get("what_it_does")
        from features.verdicts import latest_verdict
        if coin.get("symbol"):
            out["verdict"] = await latest_verdict(db(), coin["symbol"], details=False)
    return out


async def cached_xray(query: str) -> dict:
    """Same query within 10 minutes → same answer, computed once (single-flight). In a webinar hundreds of
    people paste the same coin or the same viral tip at once; this keeps it to one market lookup + one AI call."""
    import copy

    import market
    key = "xray:" + " ".join(query.strip().lower().split())[:300]
    return copy.deepcopy(await market._cached(key, int(os.environ.get("XRAY_CACHE_SECONDS", "600") or 600),
                                              lambda: run_xray(query)))


@router.post("/xray")
async def xray(body: XRayIn, request: Request, response: Response):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail={"code": "empty", "msg": "Type a coin name, link or message to check."})
    user = await optional_user(request)
    had_cookie = events.anon_id_from(request) is not None
    anon = events.ensure_anon_cookie(request, response)
    if user:
        usage = await plans.consume(db(), user, "xray")
    else:
        per_day = (await appsettings.get(db()))["anon_xray_per_day"]
        from accounts.routes import client_ip
        ip = client_ip(request)
        if not had_cookie:
            # No valid visitor cookie (cleared, forged, or a script): a real browser gets one from the page view
            # before its first check, so these share one small allowance per network instead of each getting
            # a fresh one (QA 10 Nov: the logged-out limit could be bypassed). The check also counts against
            # the cookie issued with this answer.
            await plans.anon_consume(db(), f"nocookie:{ip}", "xray",
                                     int(os.environ.get("ANON_XRAY_NOCOOKIE_PER_IP_DAY", "30") or 30))
        usage = await plans.anon_consume(db(), f"a:{anon}", "xray", per_day)
        # Per-IP backstop only (CGNAT: many visitors share one carrier IP — see OTP_MAX_PER_IP_HOUR).
        ip_cap = int(os.environ.get("ANON_XRAY_PER_IP_DAY", "1000") or 1000)
        await plans.anon_consume(db(), f"ip:{ip}", "xray", ip_cap)
    try:
        out = await cached_xray(body.query)
    except HTTPException:
        if user:
            await plans.refund(db(), user, "xray")
        raise
    out["usage"] = usage
    await events.track(db(), "xray_run", user_id=str(user["_id"]) if user else None, anon_id=anon,
                       props={"kind": out["kind"], "label": out["label"], "anon": not user})
    if user:
        await db().xray_checks.insert_one({"user_id": str(user["_id"]), "query": out["query"], "kind": out["kind"],
                                           "label": out["label"], "score": out["score"], "at": utcnow()})
    return out


@router.get("/xray/history")
async def history(user: dict = Depends(user_dep())):
    rows = db().xray_checks.find({"user_id": str(user["_id"])}).sort("at", -1).limit(30)
    return {"items": [{"query": r["query"], "kind": r["kind"], "label": r["label"], "score": r["score"], "at": iso(r["at"])}
                      async for r in rows]}
