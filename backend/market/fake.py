"""Deterministic fake market for tests and QA mode — no network.

Prices follow rough historical anchor points (monthly, USD) with seeded daily noise,
so What If has a real 2021 peak / 2022 crash and charts look plausible.
SAMPLE DATA ONLY — never shown in production (vendor_mode refuses fake there).
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import date, timedelta
from typing import Optional

# (YYYY-MM, price) anchors. Interpolated log-linearly.
ANCHORS: dict[str, list[tuple[str, float]]] = {
    "BTC": [("2015-12", 430), ("2016-12", 960), ("2017-06", 2500), ("2017-12", 14000), ("2018-06", 6400),
            ("2018-12", 3700), ("2019-06", 11000), ("2019-12", 7200), ("2020-03", 6400), ("2020-09", 10800),
            ("2020-12", 29000), ("2021-04", 58000), ("2021-07", 33000), ("2021-11", 61000), ("2022-01", 38500),
            ("2022-06", 20000), ("2022-12", 16500), ("2023-06", 30400), ("2023-12", 42300), ("2024-03", 71000),
            ("2024-08", 59000), ("2024-12", 93500), ("2025-04", 84000), ("2025-08", 108000), ("2025-10", 112000),
            ("2026-02", 98000), ("2026-06", 88000), ("2026-11", 92000)],
    "ETH": [("2015-12", 0.9), ("2016-12", 8), ("2017-06", 300), ("2017-12", 720), ("2018-06", 450), ("2018-12", 130),
            ("2019-06", 290), ("2019-12", 130), ("2020-03", 135), ("2020-12", 740), ("2021-05", 2700),
            ("2021-07", 2300), ("2021-11", 4600), ("2022-06", 1070), ("2022-12", 1200), ("2023-12", 2280),
            ("2024-03", 3600), ("2024-08", 2500), ("2024-12", 3330), ("2025-04", 1800), ("2025-08", 4300),
            ("2026-02", 3100), ("2026-11", 3400)],
    "SOL": [("2020-05", 0.8), ("2020-12", 1.5), ("2021-05", 35), ("2021-11", 210), ("2022-06", 33), ("2022-12", 10),
            ("2023-06", 18), ("2023-12", 101), ("2024-03", 200), ("2024-08", 140), ("2024-12", 190),
            ("2025-04", 125), ("2025-09", 210), ("2026-02", 170), ("2026-11", 160)],
    "XRP": [("2015-12", 0.006), ("2017-06", 0.27), ("2017-12", 2.0), ("2018-12", 0.35), ("2020-12", 0.22),
            ("2021-04", 1.6), ("2022-06", 0.32), ("2023-12", 0.62), ("2024-10", 0.52), ("2024-12", 2.1),
            ("2025-07", 3.1), ("2026-11", 2.4)],
}
BASE: dict[str, tuple[str, float, float, int]] = {   # name, price now, mcap (bn USD), rank
    "BTC": ("Bitcoin", 0, 1830, 1), "ETH": ("Ethereum", 0, 410, 2), "USDT": ("Tether", 1.0, 160, 3),
    "XRP": ("XRP", 0, 140, 4), "BNB": ("BNB", 640, 92, 5), "SOL": ("Solana", 0, 82, 6), "USDC": ("USD Coin", 1.0, 70, 7),
    "DOGE": ("Dogecoin", 0.21, 31, 8), "TRX": ("TRON", 0.27, 25, 9), "ADA": ("Cardano", 0.66, 23, 10),
    "LINK": ("Chainlink", 17.5, 11, 11), "AVAX": ("Avalanche", 27.0, 11, 12), "SUI": ("Sui", 3.4, 11, 13),
    "TON": ("Toncoin", 3.1, 8, 14), "SHIB": ("Shiba Inu", 0.0000142, 8.4, 15), "DOT": ("Polkadot", 4.1, 6.3, 16),
    "LTC": ("Litecoin", 88.0, 6.6, 17), "PEPE": ("Pepe", 0.0000105, 4.4, 24), "NEAR": ("NEAR Protocol", 2.9, 3.5, 28),
    "WIF": ("dogwifhat", 0.92, 0.9, 70), "BONK": ("Bonk", 0.000021, 1.6, 55), "FLOKI": ("FLOKI", 0.000095, 0.9, 72),
}
DESCRIPTIONS = {
    "BTC": "The first cryptocurrency: a fixed supply of 21 million coins, moved without a bank.",
    "ETH": "A blockchain for apps and tokens; ETH pays the network's fees.",
    "SOL": "A fast, low-fee blockchain popular for trading apps and meme coins.",
    "XRP": "A payments network built for moving money across borders.",
    "BNB": "The coin of the Binance exchange and its BNB Chain.",
    "DOGE": "A meme coin that became a top-10 coin; unlimited supply.",
}
BINANCE_LIST = ["BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "TRX", "ADA", "LINK", "AVAX", "SUI", "TON", "SHIB", "DOT",
                "LTC", "PEPE", "NEAR", "WIF", "BONK", "FLOKI", "ARB", "OP", "APT", "UNI"]
KUCOIN_LIST = BINANCE_LIST + ["KCS", "ONDO", "JUP"]
NEW_POOL = [("KAITO", "Kaito"), ("BERA", "Berachain"), ("HYPE", "Hyperliquid"), ("MOVE", "Movement"),
            ("PENGU", "Pudgy Penguins"), ("VIRTUAL", "Virtuals Protocol"), ("USUAL", "Usual"), ("ME", "Magic Eden"),
            ("LAYER", "Solayer"), ("ANIME", "Animecoin")]
TRENDING_POOL = ["PEPE", "WIF", "BONK", "FLOKI", "SUI", "TON", "NEAR", "DOGE", "SHIB", "HYPE", "KAITO"]


def _rng(*parts) -> random.Random:
    h = hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _month_mid(ym: str) -> date:
    y, m = map(int, ym.split("-"))
    return date(y, m, 15)


def _interp(anchors: list[tuple[str, float]], d: date) -> float:
    pts = [(_month_mid(a), p) for a, p in anchors]
    if d <= pts[0][0]:
        return pts[0][1]
    for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
        if d <= d1:
            t = (d - d0).days / max(1, (d1 - d0).days)
            return math.exp(math.log(p0) + t * (math.log(p1) - math.log(p0)))
    return pts[-1][1]


def _today() -> date:
    from growth.clock import IST, utcnow
    return utcnow().astimezone(IST).date()


class FakeMarket:
    def _series(self, symbol: str, days: int) -> list[tuple[str, float]]:
        end = _today()
        start = end - timedelta(days=days - 1)
        out = []
        if symbol in ANCHORS:
            anchors = ANCHORS[symbol]
            vol = 0.022
        elif symbol in BASE:
            px = BASE[symbol][1]
            anchors = [("2020-01", px * 0.35), ("2021-11", px * 2.4), ("2022-12", px * 0.4), ("2024-12", px * 1.5),
                       (end.strftime("%Y-%m"), px)]
            vol = 0.035
        else:
            r = _rng("base", symbol)
            px = 10 ** r.uniform(-4, 1)
            anchors = [((end - timedelta(days=400)).strftime("%Y-%m"), px * 0.5), (end.strftime("%Y-%m"), px)]
            vol = 0.06
        noise = 0.0
        d = start - timedelta(days=60)
        while d <= end:                      # warm up the noise so the first day is stable
            r = _rng("n", symbol, d.isoformat())
            noise = noise * 0.93 + r.gauss(0, vol)
            if d >= start:
                out.append((d.isoformat(), round(_interp(anchors, d) * math.exp(noise), 10)))
            d += timedelta(days=1)
        return out

    def _coin(self, symbol: str) -> Optional[dict]:
        if symbol not in BASE and symbol not in dict(NEW_POOL):
            return None
        name, _, mcap_bn, rank = BASE.get(symbol, (dict(NEW_POOL).get(symbol, symbol), 0, 0.4, 180))
        if symbol in ("USDT", "USDC"):
            px, prev = 1.0, 1.0
        else:
            s = self._series(symbol, 2)
            prev, px = s[0][1], s[-1][1]
        mcap = mcap_bn * 1e9
        vol_ratio = 0.035 + _rng("v", symbol).random() * 0.06
        ath = max(p for _, p in self._series(symbol, 1900)) if symbol not in ("USDT", "USDC") else 1.0
        genesis = {"BTC": "2009-01-03", "ETH": "2015-07-30", "SOL": "2020-03-16", "XRP": "2012-06-02"}.get(
            symbol, "2019-01-01" if symbol in BASE else (_today() - timedelta(days=40)).isoformat())
        return {"id": symbol.lower(), "symbol": symbol, "name": name, "rank": rank, "price_usd": px,
                "market_cap_usd": mcap, "volume_24h_usd": mcap * vol_ratio,
                "change_24h": round((px / prev - 1) * 100, 2) if prev else 0.0, "ath_usd": ath,
                "chain": {"SOL": "solana", "BONK": "solana", "WIF": "solana", "PEPE": "ethereum", "SHIB": "ethereum",
                          "LINK": "ethereum", "FLOKI": "ethereum"}.get(symbol),
                "contract": None, "genesis_date": genesis, "categories": [],
                "description": DESCRIPTIONS.get(symbol, f"{name} is a crypto token."), "homepage": None}

    async def top_coins(self, n: int) -> list[dict]:
        rows = [self._coin(s) for s in sorted(BASE, key=lambda k: BASE[k][3])]
        return [r for r in rows if r][:n]

    async def prices(self, symbols: list[str]) -> dict[str, dict]:
        return {s: c for s in symbols if (c := self._coin(s))}

    async def history(self, symbol: str, days: int) -> list[tuple[str, float]]:
        if symbol in ("USDT", "USDC"):
            end = _today()
            return [((end - timedelta(days=i)).isoformat(), 1.0) for i in range(days - 1, -1, -1)]
        return self._series(symbol, days)

    async def search(self, query: str) -> Optional[dict]:
        q = query.strip()
        if q.startswith("0x") and len(q) == 42 or (len(q) >= 32 and q.isalnum() and not q.isalpha()):
            r = _rng("contract", q.lower())
            age = r.randint(2, 60)
            mcap = 10 ** r.uniform(4.5, 6.5)
            return {"id": None, "symbol": "TKN" + q[-3:].upper(), "name": "Unverified token", "rank": None,
                    "price_usd": 10 ** r.uniform(-8, -4), "market_cap_usd": mcap, "volume_24h_usd": mcap * r.uniform(0.01, 3),
                    "change_24h": round(r.uniform(-60, 400), 1), "ath_usd": None, "chain": "ethereum" if q.startswith("0x") else "solana",
                    "contract": q, "genesis_date": (_today() - timedelta(days=age)).isoformat(), "categories": ["Meme"],
                    "description": "", "homepage": None, "unlisted": True}
        sym = q.upper()
        for s, (name, *_rest) in BASE.items():
            if sym == s or q.lower() == name.lower():
                return self._coin(s)
        for s, name in NEW_POOL:
            if sym == s or q.lower() == name.lower():
                return self._coin(s)
        return None

    async def global_stats(self) -> dict:
        btc = self._coin("BTC")
        total = sum(v[2] for v in BASE.values()) * 1e9 * 1.18
        return {"total_mcap_usd": total, "btc_dominance_pct": round(btc["market_cap_usd"] / total * 100, 1)}

    async def fear_greed(self) -> dict:
        v = _rng("fng", _today().isoformat()).randint(28, 74)
        label = ("Extreme Fear" if v < 25 else "Fear" if v < 45 else "Neutral" if v <= 55 else
                 "Greed" if v < 75 else "Extreme Greed")
        return {"value": v, "label": label}

    async def trending(self) -> list[dict]:
        r = _rng("trend", _today().isoformat())
        picks = r.sample(TRENDING_POOL, 6)
        out = []
        for s in picks:
            c = self._coin(s) or {"symbol": s, "name": dict(NEW_POOL).get(s, s), "price_usd": 1.0, "change_24h": 0}
            out.append({"symbol": s, "name": c["name"], "id": s.lower(), "rank": c.get("rank"),
                        "price_usd": c["price_usd"], "change_24h": round(r.uniform(-8, 35), 1)})
        return out

    async def listings(self, venue: str) -> list[str]:
        base = list(BINANCE_LIST if venue == "binance" else KUCOIN_LIST)
        # One or two "new" listings appear every few days (sample data).
        days = (_today() - date(2026, 1, 1)).days
        k = (days // 3) % len(NEW_POOL)
        extra = [NEW_POOL[k][0]] + ([NEW_POOL[(k + 3) % len(NEW_POOL)][0]] if venue == "kucoin" else [])
        older = [NEW_POOL[(k - i) % len(NEW_POOL)][0] for i in range(1, 3)]
        return sorted(set(base + extra + older))
