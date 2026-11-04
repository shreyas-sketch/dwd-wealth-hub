"""Seed a realistic load-test database: 10,000+ members with 30 days of history.

    MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=coinzeye_load JWT_SECRET=<same as the app> \
        python scripts/seed_load.py [--users 10000]

Idempotent: every seeded row carries `seed: "load"` and is replaced on each run (real rows are untouched).
JWT_SECRET (or EXCHANGE_VAULT_KEY) must match the app so the sealed demo exchange keys open.

Mix: 70% free (trial over), 15% on trial, 10% on ₹2,000 (lite), 5% on ₹5,000 (pro).
Phones: +91 70000 00000 … (+917000000000 + i). Linked demo exchanges for paid members with Autopilot plans.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from pymongo import InsertOne, MongoClient  # noqa: E402

FEATURE_EVENTS = ["whatif_run", "xray_run", "verdicts_viewed", "forecast_run", "debate_run", "plan_saved",
                  "paper_trade", "airdrop_step", "chart_read", "ask_asked", "radar_viewed", "news_viewed",
                  "calendar_viewed", "p2p_viewed"]
COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "TRX", "AVAX", "LINK"]
ALLOC = {"safe": [("BTC", 70), ("ETH", 20), ("USDT", 10)],
         "moderate": [("BTC", 50), ("ETH", 30), ("SOL", 10), ("XRP", 10)],
         "aggressive": [("BTC", 40), ("ETH", 25), ("SOL", 20), ("XRP", 15)]}
SEED = {"seed": "load"}


def phone_for(i: int) -> str:
    return f"+9170{i:08d}"


def tier_for(i: int) -> str:
    r = i % 100
    return "free" if r < 70 else "trial" if r < 85 else "lite" if r < 95 else "pro"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=10_000)
    ap.add_argument("--events-per-user", type=int, default=30)
    a = ap.parse_args()
    os.environ.setdefault("JWT_SECRET", "load-test-secret-0123456789abcdef")
    from crypto import vault

    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"), tz_aware=True)[
        os.environ.get("DB_NAME", "coinzeye_load")]
    t0 = time.time()
    for c in ("users", "subscriptions", "crypto_plans", "paper", "paper_history", "watchlists", "usage",
              "ask_threads", "inbox", "events", "exchange_links", "dca_plans", "dca_buys", "airdrop_progress"):
        db[c].delete_many(SEED)
    rnd = random.Random(42)
    now = datetime.now(timezone.utc)
    month = now.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m")
    sealed = vault.seal({"api_key": "loadkey-0000", "api_secret": "loadsecret-0000", "passphrase": "loadpass"})

    users, ops = [], {k: [] for k in ("subscriptions", "crypto_plans", "paper", "paper_history", "watchlists", "usage",
                                      "ask_threads", "inbox", "events", "exchange_links", "dca_plans")}
    for i in range(a.users):
        tier = tier_for(i)
        created = now - timedelta(days=rnd.uniform(0, 30), minutes=rnd.randint(0, 600))
        trial_end = created + timedelta(days=3)
        if tier == "trial":
            created = now - timedelta(hours=rnd.uniform(1, 60))
            trial_end = now + timedelta(days=rnd.uniform(0.2, 2.5))
        u = {"phone": phone_for(i), "name": f"Member {i}", "role": "user", "status": "active",
             "created_at": created, "first_login_at": created, "last_login_at": created + timedelta(days=rnd.uniform(0, 5)),
             "phone_verified_at": created, "trial_ends_at": trial_end,
             "acquisition": {"source": rnd.choice(["webinar", "webinar", "webinar", "meta_ads", "organic"]),
                             "utm": {"utm_source": "webinar"}, "at": created}, **SEED}
        users.append(u)
    t = time.time()
    res = db.users.insert_many(users, ordered=False)
    print(f"users: {len(res.inserted_ids)} in {time.time() - t:.1f}s")

    for i, (u, uid_obj) in enumerate(zip(users, res.inserted_ids)):
        uid, tier = str(uid_obj), tier_for(i)
        if tier in ("lite", "pro"):
            start = now - timedelta(days=rnd.uniform(1, 25))
            ops["subscriptions"].append(InsertOne({"_id": f"sub_load_{i}", "user_id": uid, "plan": tier, "status": "active",
                                                   "current_end": start + timedelta(days=31), "created_at": start,
                                                   "updated_at": start, **SEED}))
        if rnd.random() < 0.6:
            risk = rnd.choice(list(ALLOC))
            pid = uuid.uuid4().hex[:16]
            ops["crypto_plans"].append(InsertOne({
                "_id": pid, "user_id": uid, "goal_name": rnd.choice(["1 BTC", "Kids' education", "Retirement", "House"]),
                "target_inr": rnd.choice([1_000_000, 2_500_000, 5_000_000, 10_000_000]),
                "lump_sum_inr": rnd.choice([0, 25_000, 50_000, 100_000]), "monthly_inr": rnd.choice([2000, 5000, 10000, 25000]),
                "years": rnd.choice([3, 5, 10]), "risk": risk,
                "allocation": [{"symbol": s, "pct": p} for s, p in ALLOC[risk]], "paper_started": True,
                "created_at": u["created_at"], "updated_at": u["created_at"], **SEED}))
            if rnd.random() < 0.7:
                pos = {s: {"qty": 90_000 * p / 100 / {"BTC": 8_000_000, "ETH": 300_000, "SOL": 14_000, "XRP": 200}.get(s, 1),
                           "cost_inr": 90_000 * p / 100} for s, p in ALLOC[risk] if s != "USDT"}
                ops["paper"].append(InsertOne({"_id": uid, "start_inr": 100_000.0, "cash_inr": 10_000.0, "positions": pos,
                                               "plan_id": pid, "started_at": u["created_at"], "trades": [], **SEED}))
                for d in range(min(30, (now - u["created_at"]).days)):
                    day = (now - timedelta(days=d)).date().isoformat()
                    ops["paper_history"].append(InsertOne({"_id": f"{uid}:{day}", "user_id": uid, "date": day,
                                                           "value_inr": 100_000 * (1 + rnd.uniform(-0.15, 0.2)), **SEED}))
        if rnd.random() < 0.3:
            ops["watchlists"].append(InsertOne({"_id": uid, "symbols": rnd.sample(COINS, rnd.randint(1, 4)), **SEED}))
        ops["usage"].append(InsertOne({"_id": f"{uid}:{month}", "user_id": uid, "month": month,
                                       "xray": rnd.randint(0, 25), "forecast": rnd.randint(0, 8), "debate": rnd.randint(0, 5),
                                       "chart": rnd.randint(0, 6), "ask": rnd.randint(0, 40) if tier in ("pro", "trial") else 0,
                                       **SEED}))
        if tier in ("pro", "trial") and rnd.random() < 0.5:
            msgs = []
            for _ in range(rnd.randint(1, 4)):
                msgs += [{"role": "user", "text": "What is DCA?", "at": now},
                         {"role": "assistant", "text": "DCA means buying a fixed amount on a schedule…" * 3,
                          "sources": [{"title": "Session 2", "snippet": "…"}], "at": now}]
            ops["ask_threads"].append(InsertOne({"_id": uuid.uuid4().hex[:16], "user_id": uid, "title": "What is DCA?",
                                                 "messages": msgs, "created_at": now, "updated_at": now, **SEED}))
        for k in range(3):
            ops["inbox"].append(InsertOne({"_id": uuid.uuid4().hex, "user_id": uid, "kind": rnd.choice(["verdict", "radar", "system"]),
                                           "title": "Verdict changed: ETH is now Neutral", "body": "…", "link": "/app/verdicts",
                                           "at": now - timedelta(hours=rnd.uniform(0, 600)), "read": rnd.random() < 0.6, **SEED}))
        span = max(1.0, (now - u["created_at"]).total_seconds())
        for _ in range(rnd.randint(a.events_per_user // 2, a.events_per_user * 3 // 2)):
            ops["events"].append(InsertOne({"_id": uuid.uuid4().hex, "name": rnd.choice(FEATURE_EVENTS + ["login", "page_view"]),
                                            "ts": u["created_at"] + timedelta(seconds=rnd.uniform(0, span)),
                                            "user_id": uid, "props": {}, "src": "server", **SEED}))
        if tier in ("lite", "pro") and rnd.random() < 0.6:
            venue = rnd.choice(["kucoin", "binance"])
            ops["exchange_links"].append(InsertOne({
                "_id": f"{uid}:{venue}", "user_id": uid, "venue": venue, "sealed": sealed, "key_tail": "••••0000",
                "status": "active", "failures": 0, "failure_reason": None,
                "permissions": {"read": True, "trade": True, "withdraw": False, "ip_restricted": False, "earn": False},
                "linked_at": u["created_at"], "verified_at": now, "updated_at": now, **SEED}))
            nxt = now - timedelta(minutes=rnd.randint(1, 600)) if rnd.random() < 0.4 else now + timedelta(days=rnd.randint(1, 20))
            ops["dca_plans"].append(InsertOne({
                "_id": uuid.uuid4().hex[:16], "user_id": uid, "kind": "coin", "venue": venue,
                "coin": "BTC" if tier == "lite" else rnd.choice(["BTC", "ETH", "SOL"]), "basket_id": None, "basket_name": None,
                "amount_inr": rnd.choice([1000, 2000, 5000]), "frequency": "monthly" if tier == "lite" else rnd.choice(["weekly", "monthly"]),
                "weekday": rnd.randint(0, 6), "day": rnd.randint(1, 28), "status": "active", "next_at": nxt,
                "created_at": u["created_at"], "updated_at": now, "last_error": None, **SEED}))
    for coll, rows in ops.items():
        t = time.time()
        for k in range(0, len(rows), 5000):
            db[coll].bulk_write(rows[k:k + 5000], ordered=False)
        print(f"{coll}: {len(rows)} in {time.time() - t:.1f}s")
    print(f"done in {time.time() - t0:.1f}s · users total {db.users.count_documents({})} · events total {db.events.count_documents({})}")


if __name__ == "__main__":
    main()
