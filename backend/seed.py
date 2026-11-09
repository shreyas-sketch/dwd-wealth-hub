"""Demo content for QA_MODE (and a starting point for the team). Idempotent: only fills empty collections.

All of this is SAMPLE content written for testing — the team replaces it in the admin panel.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from growth.clock import IST, utcnow

log = logging.getLogger("seed")

KB_SAMPLE = [
    ("Session 1 — Crypto basics for beginners", """
Let's start simple. Bitcoin is digital money with a fixed supply: there will only ever be 21 million coins. Nobody can
print more, and that is why people compare it to digital gold. Ethereum is different. It is a network where apps run,
and ETH is the fuel you pay to use it. Almost everything else is a token built on top of these networks.

When you buy crypto in India, you usually buy on an exchange like KuCoin or Binance using USDT. USDT is a stable coin
that tracks the US dollar. So the usual path is: rupees to USDT through P2P, then USDT to Bitcoin or Ethereum.

The most important rule for a beginner: only put in money you won't need for at least three to five years. Crypto
falls 30, 50, even 70 percent in bad years. If that would scare you into selling, the amount is too big.
Start with an amount that lets you sleep at night, learn how the exchange works, and grow slowly.

Tax in India: gains on crypto are taxed at 30 percent, and losses on one coin can't be set off against gains on
another. There is also 1 percent TDS on transfers. Keep records of every buy and sell for your CA.
"""),
    ("Session 2 — Why we do SIP (DCA) in crypto", """
Most people lose money in crypto because they try to time the market. They buy when everyone is excited and the
price is at the top, then they panic and sell when it falls. A SIP, or DCA, fixes this. You buy a fixed rupee
amount every week or every month, whatever the price.

When the price is low, your fixed amount buys more coins. When the price is high, it buys fewer. Over a few years
your average cost comes out reasonable without you having to guess anything. No timing. No panic. Just discipline.

How much? Look at your monthly savings and decide a share for crypto. For most people starting out, 5 to 10 percent
of their investments is plenty. Keep Bitcoin and Ethereum as the core — say 70 to 80 percent — and only a small
part in other coins.

Stick to the plan when the market crashes. That is exactly when the SIP does its best work. If you stop your SIP
every time the price falls, you lose the whole benefit.
"""),
    ("Session 3 — Wallet and exchange safety", """
Safety first, always. Your seed phrase — the 12 or 24 words — is the master key to your wallet. Write it on paper,
keep it somewhere safe, and never type it into any website, never send it on WhatsApp, never share it with anyone
who calls themselves support. Real support will never ask for it. Anyone who has it can take everything.

On exchanges, switch on two-factor authentication and set an anti-phishing code. When you create an API key for an
app, give it permission to read and trade only. Never switch on withdrawals for an API key. That way, even if the
key leaks, nobody can move your coins out.

Common scams in India: task jobs that pay you small amounts first and then ask you to invest; Telegram groups that
promise guaranteed daily returns; fake exchange websites with a slightly different address; and people pretending to
be from KuCoin or Binance saying your account will be blocked. If someone promises guaranteed returns, it's a scam.

Before you buy any new coin, check it: how big is it, how long has it existed, is it listed on major exchanges,
and do a few wallets hold most of it? New coins with tiny market size and huge hype are where most people lose money.
"""),
    ("Session 4 — Reading a chart without getting lost", """
You don't need twenty indicators. Start with three things. First, the trend: are the highs and lows going up, down
or sideways? Second, support and resistance: price levels where the coin has bounced before or been rejected before.
Third, RSI: above 70 means the move is stretched and a pullback is common; below 30 means it is oversold and bounces
often start there.

Use the daily chart for decisions, not the 5-minute chart. Short charts are mostly noise and push you into
over-trading. And remember, a chart shows probabilities, not certainties. Always decide in advance how much you are
willing to lose on a trade, and never use leverage while you are learning.
"""),
]


async def seed_demo(db) -> dict:
    now = utcnow()
    from jobs.registry import Ctx
    out = {}
    from features import calendar as cal
    await cal.ensure_seed(db)
    if not await db.kb_docs.count_documents({}):
        from features.ask import ingest
        for title, text in KB_SAMPLE:
            await ingest(db, title, text)
        out["kb"] = len(KB_SAMPLE)
    if not await db.etf_flows.count_documents({}):
        today = now.astimezone(IST).date()
        for i, v in enumerate([412.5, -138.2, 266.0, 95.4, -54.1]):
            d = (today - timedelta(days=i + 1)).isoformat()
            await db.etf_flows.insert_one({"_id": d, "date": d, "net_usd_m": v, "note": "Sample figure (QA)"})
    if not await db.verdicts.count_documents({}):
        from features.verdicts import job_daily
        # yesterday first, so today's run can show a changed verdict
        out["verdicts_prev"] = await job_daily(Ctx(db, now - timedelta(days=1)))
        out["verdicts"] = await job_daily(Ctx(db, now))
        # Sample: show one changed verdict so the "changed" badge is visible in QA.
        day = now.astimezone(IST).date().isoformat()
        v = await db.verdicts.find_one({"date": day, "symbol": "ETH"})
        if v:
            await db.verdicts.update_one({"_id": v["_id"]}, {"$set": {
                "changed_from": "Bearish" if v["verdict"] != "Bearish" else "Neutral"}})
    if not await db.verdict_outcomes.count_documents({}):
        # 60 days of rule-made verdicts (each from the history that day could see), scored, for Admin › Verdict accuracy
        from features.accuracy import job_score, seed_backtest
        out["verdicts_backtest"] = await seed_backtest(db)
        out["verdict_scoring"] = await job_score(Ctx(db, now))
    if not await db.picks.count_documents({}):
        from features.verdicts import suggest_picks, week_of
        import market
        picks = await suggest_picks(db)
        px = await market.prices([p["symbol"] for p in picks])
        for p in picks:
            p["price_at_pick_usd"] = (px.get(p["symbol"]) or {}).get("price_usd", 0) * 0.97
        await db.picks.insert_one({"_id": week_of(), "published": True, "picks": picks, "updated_at": now})
    if not await db.airdrops.count_documents({}):
        rows = [
            {"name": "Sample L2 testnet campaign", "coin": None, "chain": "Ethereum", "reward": "Possible future token",
             "deadline": (now + timedelta(days=21)).date().isoformat(), "link": "https://example.com/l2-testnet",
             "description": "Use the test network a few times. No real money needed — never pay to 'claim'.",
             "steps": [{"id": "s1", "text": "Create a fresh MetaMask wallet only for airdrops"},
                       {"id": "s2", "text": "Get free test ETH from the official faucet"},
                       {"id": "s3", "text": "Make 3 swaps on the testnet app"},
                       {"id": "s4", "text": "Come back weekly for 4 weeks"}]},
            {"name": "Sample KuCoin GemPool-style event", "coin": "SUI", "chain": "Sui", "reward": "Share of a token pool",
             "deadline": (now + timedelta(days=7)).date().isoformat(), "link": "https://www.kucoin.com",
             "description": "Stake coins you already hold for a few days to earn a new token. Check the token with X-Ray before selling or holding.",
             "steps": [{"id": "s1", "text": "Complete KYC on KuCoin"}, {"id": "s2", "text": "Read the event rules on the official page"},
                       {"id": "s3", "text": "Stake only what you planned to hold anyway"}]},
            {"name": "Sample Solana app points program", "coin": None, "chain": "Solana", "reward": "Points → maybe tokens",
             "deadline": (now + timedelta(days=45)).date().isoformat(), "link": "https://example.com/sol-points",
             "description": "Earn points by using the app. Points may or may not turn into tokens.",
             "steps": [{"id": "s1", "text": "Use a separate Phantom wallet with a small amount"},
                       {"id": "s2", "text": "Do one swap a week"}, {"id": "s3", "text": "Never approve unknown tokens"}]},
            {"name": "Sample ended campaign", "coin": None, "chain": "Base", "reward": "Ended", "status": "ended",
             "deadline": (now - timedelta(days=5)).date().isoformat(), "link": None, "description": "Kept for reference.",
             "steps": [{"id": "s1", "text": "Nothing to do"}]},
        ]
        from features.airdrops import AirdropIn, save
        for r in rows:
            await save(AirdropIn(**{"status": "live", **r}))
    if not await db.baskets.count_documents({}):
        from features.baskets import BasketIn, save
        for b in [
            {"name": "Bitcoin + Ethereum Core", "theme": "Core", "description": "The two biggest coins. The base of most long-term plans.",
             "coins": [{"symbol": "BTC", "weight_pct": 70}, {"symbol": "ETH", "weight_pct": 30}],
             "risk_note": "Lowest risk in crypto — still falls 50%+ in bad years."},
            {"name": "Top 5 Blue Chips", "theme": "Large caps", "description": "Spread across the five biggest non-stable coins.",
             "coins": [{"symbol": "BTC", "weight_pct": 40}, {"symbol": "ETH", "weight_pct": 25}, {"symbol": "SOL", "weight_pct": 15},
                       {"symbol": "XRP", "weight_pct": 10}, {"symbol": "BNB", "weight_pct": 10}],
             "risk_note": "Medium-high risk."},
            {"name": "Solana Ecosystem", "theme": "Theme", "description": "Solana plus large projects that run on it.",
             "coins": [{"symbol": "SOL", "weight_pct": 60}, {"symbol": "WIF", "weight_pct": 20}, {"symbol": "BONK", "weight_pct": 20}],
             "risk_note": "High risk: meme coins can fall 80–90%."},
        ]:
            await save(BasketIn(**b))
    if not await db.crypto_events.count_documents({"source": {"$ne": "seed"}}):
        from features.calendar import EventIn, save as save_ev
        today = now.astimezone(IST).date()
        for off, title, kind, coins, impact, note in [
            (1, "US Fed interest-rate decision", "macro", ["BTC", "ETH"], "high", "Rate surprises move all risk assets, crypto included. (Sample date)"),
            (4, "Token unlock: 3% of SUI supply", "unlock", ["SUI"], "medium", "New supply can add selling pressure. (Sample)"),
            (9, "Ethereum network upgrade (testnet)", "upgrade", ["ETH"], "medium", "Upgrades can be delayed. (Sample)"),
            (12, "New listing on KuCoin", "listing", ["KAITO"], "low", "New listings are very volatile. (Sample)"),
            (20, "SEC decision on a spot SOL ETF", "etf", ["SOL"], "high", "Decisions are often delayed. (Sample)"),
        ]:
            await save_ev(EventIn(date=(today + timedelta(days=off)).isoformat(), title=title, kind=kind, coins=coins,
                                  impact=impact, note=note))
    if not await db.radar_items.count_documents({}):
        import market
        from features.radar import job_scan
        for venue in ("binance", "kucoin"):           # pretend yesterday's lists lacked the newest coins
            syms = await market.listings(venue)
            from market.fake import NEW_POOL
            newest = {s for s, _ in NEW_POOL[:4]}
            await db.listing_snapshots.replace_one({"_id": venue}, {"_id": venue, "symbols": [s for s in syms if s not in newest],
                                                                    "at": now - timedelta(days=1)}, upsert=True)
        out["radar"] = await job_scan(Ctx(db, now))
    if not await db.news.count_documents({}):
        from features.news import job_fetch
        out["news"] = await job_fetch(Ctx(db, now))
    log.info("QA seed: %s", out)
    return out
