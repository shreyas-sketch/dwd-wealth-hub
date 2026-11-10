"""Second 10 Nov live review: spoofed client IPs, unknown sites shown as safe, stale radar X-Rays."""
from datetime import timedelta

from starlette.requests import Request


def _req(headers: dict, peer="10.0.0.5") -> Request:
    return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                    "client": (peer, 1234)})


# ---------------------------------------------------------------- client IP can't be chosen by the client ----
def test_client_ip_ignores_headers_the_client_can_forge(monkeypatch):
    from accounts.routes import client_ip
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    # Railway's edge appends the visitor's address; whatever the visitor sent comes before it.
    assert client_ip(_req({"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "9.9.9.9, 81.2.69.142"})) == "81.2.69.142"
    assert client_ip(_req({"cf-connecting-ip": "1.1.1.1"})) == "10.0.0.5"
    # Railway's own internal hop (changes per request) is skipped, so one visitor is one count (QA 10 Nov).
    for hop in ("100.64.0.2", "100.97.13.8", "10.1.2.3", "fd12::1"):
        assert client_ip(_req({"x-forwarded-for": f"9.9.9.9, 81.2.69.142, {hop}"})) == "81.2.69.142"
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")              # e.g. Cloudflare in front of Railway
    assert client_ip(_req({"x-forwarded-for": "9.9.9.9, 82.3.4.5, 172.64.1.1, 100.64.0.9"})) == "82.3.4.5"
    monkeypatch.setenv("CLIENT_IP_HEADER", "cf-connecting-ip")  # only when a proxy overwrites it
    assert client_ip(_req({"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "81.2.69.142"})) == "1.1.1.1"


def test_anon_xray_one_network_is_one_count_behind_changing_internal_hops(client, monkeypatch):
    monkeypatch.setenv("ANON_XRAY_NOCOOKIE_PER_IP_DAY", "3")
    codes = []
    for i in range(5):
        client.cookies.clear()
        codes.append(client.post("/api/xray", json={"query": "SOL"},
                                 headers={"x-forwarded-for": f"81.2.69.142, 100.64.{i}.{i + 1}"}).status_code)
    assert codes == [200, 200, 200, 402, 402]


def test_anon_xray_forged_ip_headers_get_no_fresh_check(client, monkeypatch):
    monkeypatch.setenv("ANON_XRAY_NOCOOKIE_PER_IP_DAY", "3")
    codes = []
    for i in range(6):
        client.cookies.clear()
        codes.append(client.post("/api/xray", json={"query": "SOL"}, headers={
            "cf-connecting-ip": f"100.64.{i}.1", "x-forwarded-for": f"100.65.{i}.1, 81.2.69.142"}).status_code)
    assert codes == [200, 200, 200, 402, 402, 402]


# ---------------------------------------------------------------- unknown sites are never "Looks safe" ----
async def test_unknown_site_is_risky_and_known_site_still_safe():
    from features.xray import run_xray
    for site in ("randomsite.com", "cryptoplus-india.com", "bitcoin-doubler.net", "usdt-earn.in"):
        out = await run_xray(site)
        assert out["label"] != "safe", (site, out["score"])
    out = await run_xray("randomsite.com")
    assert out["label"] == "unknown" and "don't know this site" in out["headline"]   # never "safe" (round 4: not "risky")
    for site in ("binance.com", "https://www.coingecko.com/en/coins/bitcoin"):
        assert (await run_xray(site))["label"] == "safe"


# ---------------------------------------------------------------- radar X-Rays are redone when stale ----
async def test_radar_redoes_checks_from_old_rules_or_over_a_day_old(mdb):
    from features.radar import job_scan
    from features.xray import XRAY_RULES_VERSION
    from growth.clock import utcnow
    from jobs.registry import Ctx
    now = utcnow()
    old = {"label": "safe", "score": 7, "red_flags": []}
    await mdb.radar_items.insert_many([
        {"_id": "trending:cg:PEPE", "symbol": "PEPE", "kind": "trending", "seen_at": now, "xray": old},  # before versions
        {"_id": "trending:cg:PENGU", "symbol": "PENGU", "kind": "trending", "seen_at": now,
         "xray": {**old, "rules": XRAY_RULES_VERSION, "checked_at": now - timedelta(days=2)}},
        {"_id": "trending:cg:BTC", "symbol": "BTC", "kind": "trending", "seen_at": now,
         "xray": {"label": "safe", "score": 0, "red_flags": ["fresh"], "rules": XRAY_RULES_VERSION, "checked_at": now}}])
    await job_scan(Ctx(db=mdb, now=now))           # PEPE may be redone as a trending coin, PENGU by the stale pass
    for sym in ("PEPE", "PENGU"):
        x = (await mdb.radar_items.find_one({"_id": f"trending:cg:{sym}"}))["xray"]
        assert x["label"] == "risky" and "Meme coin" in x["red_flags"] and x["rules"] == XRAY_RULES_VERSION, x
    assert (await mdb.radar_items.find_one({"_id": "trending:cg:BTC"}))["xray"]["red_flags"] == ["fresh"]  # left alone
