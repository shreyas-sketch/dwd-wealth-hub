"""Mongo indexes, created at startup (idempotent)."""
from __future__ import annotations

import logging

log = logging.getLogger("indexes")

INDEXES = [
    ("users", [("phone", 1)], {"unique": True, "sparse": True}),
    ("users", [("email", 1)], {"unique": True, "sparse": True}),
    ("users", [("created_at", -1)], {}),
    ("users", [("trial_ends_at", 1)], {}),                     # admin plan filter / pulse (load test)
    ("plan_grants", [("ends_at", 1)], {}),
    ("subscriptions", [("status", 1), ("current_end", 1)], {}),
    ("usage", [("user_id", 1)], {}),
    ("job_locks", [("until", 1)], {}),
    ("exchange_links", [("user_id", 1), ("status", 1)], {}),
    ("watchlists", [("symbols", 1)], {}),                      # verdict-changed + calendar fan-out
    ("crypto_plans", [("allocation.symbol", 1)], {}),
    ("dca_buys", [("coin", 1), ("user_id", 1)], {}),
    ("events", [("anon_id", 1)], {"sparse": True}),          # identify(): anon → user on sign-up
    ("otp_challenges", [("phone", 1), ("created_at", -1)], {}),
    ("otp_challenges", [("ip", 1), ("created_at", -1)], {}),
    ("otp_challenges", [("purge_at", 1)], {"expireAfterSeconds": 0}),
    ("events", [("name", 1), ("ts", 1), ("user_id", 1), ("anon_id", 1)], {}),   # covers admin reports (load test)
    ("events", [("user_id", 1), ("ts", -1)], {}),
    ("verdicts", [("date", -1), ("rank", 1)], {}),
    ("verdicts", [("symbol", 1), ("date", -1)], {}),
    ("inbox", [("user_id", 1), ("at", -1)], {}),
    ("subscriptions", [("user_id", 1), ("status", 1)], {}),
    ("plan_grants", [("user_id", 1)], {}),
    ("dca_plans", [("status", 1), ("next_at", 1)], {}),
    ("dca_buys", [("plan_id", 1), ("at", -1)], {}),
    ("dca_buys", [("user_id", 1)], {}),
    ("kb_chunks", [("tokens", 1)], {}),
    ("kb_chunks", [("doc_id", 1)], {}),
    ("job_runs", [("name", 1), ("at", -1)], {}),
    ("news", [("published_at", -1)], {}),
    ("radar_items", [("seen_at", -1)], {}),
    ("crypto_events", [("date", 1)], {}),
    ("crypto_plans", [("user_id", 1), ("created_at", 1)], {}),
    ("paper_history", [("user_id", 1), ("date", 1)], {}),
    ("xray_checks", [("user_id", 1), ("at", -1)], {}),
    ("ask_threads", [("user_id", 1), ("updated_at", -1)], {}),
    ("anon_usage", [("at", 1)], {"expireAfterSeconds": 3 * 86400}),
]


async def ensure_indexes(db) -> None:
    for coll, keys, opts in INDEXES:
        try:
            await db[coll].create_index(keys, **opts)
        except Exception as e:  # noqa: BLE001
            log.warning("index %s %s: %s", coll, keys, e)
