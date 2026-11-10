"""Regression tests for the bugs found in the 10 Nov live review."""
import pytest

from conftest import qa_login


# ---------------------------------------------------------------- 1. a failed radar check is "not checked", not Risky ----
async def test_radar_failed_xray_is_unchecked_then_retried(mdb, monkeypatch):
    import market
    from features import radar, xray
    from growth.clock import utcnow
    from jobs.registry import Ctx
    calls = {"n": 0, "fail": True}

    async def fake_xray(q):
        calls["n"] += 1
        if calls["fail"]:
            raise RuntimeError("coingecko rate budget used up")
        return {"label": "safe", "score": 0, "red_flags": []}

    async def trending():
        return [{"symbol": "BTC", "name": "Bitcoin", "price_usd": 1.0, "change_24h": 0.0}]

    async def listings(venue):
        return []
    monkeypatch.setattr(xray, "cached_xray", fake_xray)
    monkeypatch.setattr(market, "trending", trending)
    monkeypatch.setattr(market, "listings", listings)
    monkeypatch.setattr(radar, "is_on", lambda k: True)
    r = await radar.job_scan(Ctx(mdb, utcnow()))
    doc = await mdb.radar_items.find_one({"_id": "trending:cg:BTC"})
    assert doc["xray"] == {"label": "unchecked", "score": None, "red_flags": []} and r["unchecked"] == 1
    calls["fail"] = False
    await radar.job_scan(Ctx(mdb, utcnow()))                         # next scan retries it
    doc = await mdb.radar_items.find_one({"_id": "trending:cg:BTC"})
    assert doc["xray"]["label"] == "safe" and doc["xray"]["score"] == 0
    n = calls["n"]
    await radar.job_scan(Ctx(mdb, utcnow()))                         # checked coins aren't re-checked every hour
    assert calls["n"] == n


async def test_jobs_wait_for_api_budget_but_pages_do_not():
    from core.http import RateLimited, TokenBucket, patient, wait_budget
    assert wait_budget(4) == 4
    with patient(90):
        assert wait_budget(4) == 90
    b = TokenBucket(600, 60, burst=1, name="t")                      # 10 a second: next token in 0.1 s
    await b.acquire(0)
    with pytest.raises(RateLimited):
        await b.acquire(wait_budget(0))                              # page request: no waiting
    with patient(2):
        await b.acquire(wait_budget(0))                              # job: waits 0.1 s and gets it


async def test_registry_runs_jobs_patiently(mdb, monkeypatch):
    from core.http import wait_budget
    from jobs import registry
    seen = {}

    async def job(ctx):
        seen["wait"] = wait_budget(4)
        return {}
    import types
    mod = types.ModuleType("fakejobmod")
    mod.job = job
    import sys
    monkeypatch.setitem(sys.modules, "fakejobmod", mod)
    monkeypatch.setattr(registry, "JOBS", {"x": ("X", ("every", 60), "fakejobmod:job")})
    await registry.run(mdb, "x")
    assert seen["wait"] == 90


# ---------------------------------------------------------------- 2. AI verdicts: reasons visible, honest labels ----
class _Block:
    def __init__(self, type_, text=None):
        self.type, self.text = type_, text


class _Resp:
    def __init__(self, stop, blocks):
        self.stop_reason, self.content = stop, blocks


def _live_client(monkeypatch, resp, seen):
    import llm

    class Msgs:
        async def create(self, **kw):
            seen.update(kw)
            return resp

    class C:
        messages = Msgs()
    monkeypatch.setattr(llm, "mode", lambda: "live")
    monkeypatch.setattr(llm, "_client", lambda: C())
    llm._STATS.clear()


async def test_llm_sends_low_effort_and_reads_only_text_blocks(monkeypatch):
    import llm
    seen = {}
    _live_client(monkeypatch, _Resp("end_turn", [_Block("thinking"), _Block("text", '{"a": 1}')]), seen)
    out = await llm.complete_json(task="committee", system="s", prompt="p", fake=lambda: {"a": 0}, model="strong")
    assert out == {"a": 1}
    assert seen["extra_body"] == {"output_config": {"effort": "low"}} and seen["max_tokens"] == 4000
    assert llm.call_stats()[0]["ok"] == 1


@pytest.mark.parametrize("stop,words", [("max_tokens", "cut off"), ("refusal", "declined")])
async def test_llm_cut_off_or_refused_reply_is_a_recorded_failure(monkeypatch, stop, words):
    import llm
    _live_client(monkeypatch, _Resp(stop, [_Block("text", '{"a": 1')]), {})
    out = await llm.complete_json(task="committee", system="s", prompt="p", fake=lambda: {"a": 0},
                                  model="strong", fallback_on_error=True)
    assert out == {"a": 0}
    st = llm.call_stats()[0]
    assert st["task"] == "committee" and st["failed"] == 1 and words in st["last_error"]


async def test_bad_key_reason_reaches_admin(monkeypatch):
    import llm

    class AuthenticationError(Exception):
        pass

    class Msgs:
        async def create(self, **kw):
            raise AuthenticationError("Error code: 401 - invalid x-api-key")

    class C:
        messages = Msgs()
    monkeypatch.setattr(llm, "mode", lambda: "live")
    monkeypatch.setattr(llm, "_client", lambda: C())
    llm._STATS.clear()
    with pytest.raises(llm.LLMError):
        await llm.complete_json(task="xray", system="s", prompt="p", fake=lambda: {})
    assert llm.call_stats()[0]["last_error"].startswith("AuthenticationError: Error code: 401")


async def test_verdict_made_by_reflects_ai_or_rules(monkeypatch):
    import llm
    from features import verdicts
    ind = {"price": 100.0, "rsi14": 55.0, "ema20": 101.0, "ema50": 100.0, "chg7": 1.0, "chg30": 2.0, "vol30_ann": 50.0,
           "drawdown90": -5.0, "daily_vol": 0.03, "drift": 0.0}
    monkeypatch.setattr(llm, "mode", lambda: "off")

    async def off(**kw):
        raise llm.LLMError("AI is not configured (ANTHROPIC_API_KEY).")
    monkeypatch.setattr(llm, "complete_json", off)
    assert (await verdicts.committee("BTC", "Bitcoin", ind))["made_by"] == "rules"

    async def ok(**kw):
        return {"verdict": "Bullish", "confidence": 71, "summary": "s", "bull": [], "bear": [], "chair": "c"}
    monkeypatch.setattr(llm, "mode", lambda: "live")
    monkeypatch.setattr(llm, "complete_json", ok)
    out = await verdicts.committee("BTC", "Bitcoin", ind)
    assert out["made_by"] == "ai" and out["confidence"] == 71


def test_verdicts_api_says_who_made_them(seeded_client):
    d = seeded_client.get("/api/verdicts/today").json()
    assert d["coins"] and all(c["made_by"] == "rules" for c in d["coins"])     # QA mode: fake AI = backup rules
    qa_login(seeded_client, role="admin")
    assert "ai_calls" in seeded_client.get("/api/admin/vendors").json()


# ---------------------------------------------------------------- 3. top 10 = real, buyable coins ----
async def test_top_coins_skips_tokenised_wrapped_and_unlisted(monkeypatch):
    import market

    class P:
        async def top_coins(self, n):
            syms = ["BTC", "ETH", "USDT", "FIGR_HELOC", "WBTC", "STETH", "USDS", "BSC-USD", "XRP", "PAXG", "NOTLISTED", "SOL"]
            return [{"symbol": s, "name": s, "rank": i + 1} for i, s in enumerate(syms)]

    async def listings(venue):
        return ["BTC", "ETH", "XRP", "SOL", "WBTC"] if venue == "binance" else []
    monkeypatch.setattr(market, "provider", lambda: P())
    monkeypatch.setattr(market, "listings", listings)
    market.clear_cache()
    assert [c["symbol"] for c in await market.top_coins(10)] == ["BTC", "ETH", "XRP", "SOL"]


async def test_top_coins_survives_exchange_lists_being_down(monkeypatch):
    import market

    class P:
        async def top_coins(self, n):
            return [{"symbol": s, "name": s, "rank": i + 1} for i, s in enumerate(["BTC", "FIGR_HELOC", "ETH"])]

    async def listings(venue):
        raise RuntimeError("exchange down")
    monkeypatch.setattr(market, "provider", lambda: P())
    monkeypatch.setattr(market, "listings", listings)
    market.clear_cache()
    assert [c["symbol"] for c in await market.top_coins(10)] == ["BTC", "ETH"]


def test_filler_point_does_not_claim_exchange_listings():
    from features.verdicts import _BULL_FILLERS
    assert not any("every major exchange" in f.point for f in _BULL_FILLERS)


# ---------------------------------------------------------------- 4/5/7. plan projections follow the mix ----
PLAN_BODY = {"goal_name": "Flat", "target_inr": 1_000_000, "lump_sum_inr": 50_000, "monthly_inr": 5_000, "years": 5}


def test_risk_level_changes_the_projection(client):
    qa_login(client)                                     # pro trial: 3 plans
    got = {}
    for risk in ("safe", "moderate", "aggressive"):
        p = client.post("/api/plan", json={**PLAN_BODY, "risk": risk}).json()
        got[risk] = {s["key"]: s for s in p["scenarios"]}
    # safe = 70% BTC, 20% ETH, 10% USDT → 0.94 × the Bitcoin rates; USDT doesn't grow
    assert got["safe"]["good"]["annual_pct"] == round(35 * 0.94, 1)
    for k in ("good", "average"):
        assert got["safe"][k]["end_value_inr"] < got["moderate"][k]["end_value_inr"] < got["aggressive"][k]["end_value_inr"]
    assert got["safe"]["bad"]["end_value_inr"] > got["moderate"]["bad"]["end_value_inr"] > got["aggressive"]["bad"]["end_value_inr"]


def test_plan_note_mentions_usdt_only_when_the_split_has_it(client):
    qa_login(client)
    safe = client.post("/api/plan", json={**PLAN_BODY, "risk": "safe"}).json()
    moderate = client.post("/api/plan", json={**PLAN_BODY, "risk": "moderate"}).json()
    assert "USDT" in safe["note"] and "USDT" not in moderate["note"]


def test_bad_case_default_is_a_loss():
    import appsettings
    assert appsettings.DEFAULTS["scenario_rates"]["bad"] < 0


# ---------------------------------------------------------------- 6. Paper Money after a plan edit ----
def test_paper_offers_and_does_rebalance_after_plan_change(client):
    qa_login(client)
    p = client.post("/api/plan", json={**PLAN_BODY, "risk": "moderate"}).json()
    paper = client.post("/api/paper/start", json={"plan_id": p["id"]}).json()
    assert paper["plan_drift"] is None and {x["symbol"] for x in paper["positions"]} == {"BTC", "ETH", "SOL", "XRP"}
    client.put(f"/api/plan/{p['id']}", json={**PLAN_BODY, "risk": "safe"})
    drift = client.get("/api/paper").json()["plan_drift"]
    assert drift["not_in_plan"] == ["SOL", "XRP"] and drift["missing"] == []
    value_before = client.get("/api/paper").json()["value_inr"]
    after = client.post("/api/paper/rebalance").json()
    assert {x["symbol"] for x in after["positions"]} == {"BTC", "ETH"} and after["plan_drift"] is None
    assert abs(after["value_inr"] - value_before) < 1                 # same money, new split (USDT part stays cash)
    assert abs(after["cash_inr"] - value_before * 0.1 - value_before * 0.9 * 0.10) < 1


# ---------------------------------------------------------------- after-deploy data fixes ----
async def test_startup_data_fixes(mdb):
    import maintenance
    await mdb.radar_items.insert_many([
        {"_id": "trending:cg:BTC", "symbol": "BTC", "kind": "trending",
         "xray": {"label": "risky", "score": 50, "red_flags": ["Couldn't check right now"]}},
        {"_id": "trending:cg:ETH", "symbol": "ETH", "kind": "trending", "xray": {"label": "safe", "score": 0, "red_flags": []}}])
    await mdb.verdicts.insert_many([
        {"_id": "2026-11-10:FIGR_HELOC", "date": "2026-11-10", "symbol": "FIGR_HELOC", "verdict": "Bearish",
         "bull": [maintenance.OLD_CLAIM]},
        {"_id": "2026-11-10:BTC", "date": "2026-11-10", "symbol": "BTC", "verdict": "Neutral",
         "bull": ["x", maintenance.OLD_CLAIM]}])
    await mdb.verdict_outcomes.insert_one({"_id": "2026-11-03:FIGR_HELOC:7", "symbol": "FIGR_HELOC"})
    out = await maintenance.run_data_fixes(mdb)
    assert out == {"fix_legacy_radar_checks": 1, "drop_non_coin_verdicts": 1, "reword_exchange_claim": 1}
    assert (await mdb.radar_items.find_one({"_id": "trending:cg:BTC"}))["xray"]["label"] == "unchecked"
    assert (await mdb.radar_items.find_one({"_id": "trending:cg:ETH"}))["xray"]["label"] == "safe"
    assert await mdb.verdicts.count_documents({"symbol": "FIGR_HELOC"}) == 0
    assert await mdb.verdict_outcomes.count_documents({}) == 0
    assert (await mdb.verdicts.find_one({"_id": "2026-11-10:BTC"}))["bull"] == ["x", maintenance.NEW_CLAIM]
    assert await maintenance.run_data_fixes(mdb) == {}                 # idempotent


async def test_verdict_rerun_replaces_the_whole_days_list(mdb):
    from features.verdicts import job_daily
    from growth.clock import IST, utcnow
    from jobs.registry import Ctx
    now = utcnow()
    day = now.astimezone(IST).date().isoformat()
    await mdb.verdicts.insert_one({"_id": f"{day}:OLDCOIN", "date": day, "symbol": "OLDCOIN", "verdict": "Bullish",
                                   "confidence": 59, "created_at": now})
    r = await job_daily(Ctx(mdb, now))
    assert r["coins"] == 10
    assert await mdb.verdicts.count_documents({"date": day, "symbol": "OLDCOIN"}) == 0
    assert await mdb.verdicts.count_documents({"date": day}) == 10


# ---------------------------------------------------------------- logged-out X-Ray limit can't be reset ----
def test_anon_xray_cleared_or_forged_cookie_gets_no_fresh_check(client, monkeypatch):
    monkeypatch.setenv("ANON_XRAY_NOCOOKIE_PER_IP_DAY", "3")
    client.post("/api/events", json={"name": "page_view", "props": {"path": "/"}})     # the landing page sets the cookie
    assert client.post("/api/xray", json={"query": "BTC"}).status_code == 200
    assert client.post("/api/xray", json={"query": "ETH"}).status_code == 402         # 1 a day
    codes = []
    for i in range(5):                                                                   # clear or forge the cookie
        client.cookies.clear()
        client.cookies.set("cz_anon", f"forged{i:04d}abcdef")
        codes.append(client.post("/api/xray", json={"query": "SOL"}).status_code)
    assert codes == [200, 200, 200, 402, 402]                                           # only the small no-cookie allowance


def test_anon_cookie_is_signed():
    from starlette.requests import Request

    from growth import events

    def req(v):
        return Request({"type": "http", "headers": [(b"cookie", f"cz_anon={v}".encode())]})
    good = "a" * 32
    assert events.anon_id_from(req(f"{good}.{events._sign(good)}")) == good
    assert events.anon_id_from(req(good)) is None
    assert events.anon_id_from(req(f"{good}.0000000000000000")) is None


async def test_chair_sentence_reworded(mdb):
    import maintenance
    chair = f"Bearish with 59% confidence. {maintenance.OLD_CLAIM}"
    await mdb.verdicts.insert_one({"_id": "2026-11-10:TRX", "symbol": "TRX", "bull": ["x"], "chair": chair})
    assert (await maintenance.run_data_fixes(mdb))["reword_exchange_claim"] == 1
    assert (await mdb.verdicts.find_one({"_id": "2026-11-10:TRX"}))["chair"].endswith(maintenance.NEW_CLAIM)


# ---------------------------------------------------------------- X-Ray: look-alikes and meme coins ----
@pytest.mark.parametrize("url", ["blnance-bonus.com", "https://blnance.com/login", "my-kucoin-login.com",
                                 "kuc0in.com", "binance-support.xyz", "trust-wallet-help.com"])
def test_lookalike_sites_are_likely_scams(url):
    from features.xray import link_flags, score_of
    red, green = link_flags(url)
    assert score_of(red, green)[1] == "likely_scam", (url, red)


@pytest.mark.parametrize("url", ["binance.com", "https://www.kucoin.com/trade", "coingecko.com", "finance-news.com",
                                 "balance-check.com"])
def test_real_sites_and_ordinary_words_are_not_called_fakes(url):
    from features.xray import link_flags, score_of
    red, green = link_flags(url)
    assert score_of(red, green)[1] != "likely_scam", (url, red)


@pytest.mark.parametrize("q", ["PEPE", "DOGE", "SHIB"])
def test_meme_coins_never_look_safe(client, q):
    qa_login(client)
    d = client.post("/api/xray", json={"query": q}).json()
    assert d["label"] != "safe" and any(f["title"] == "Meme coin" for f in d["red_flags"]), d["label"]


def test_bitcoin_still_looks_safe(client):
    qa_login(client)
    assert client.post("/api/xray", json={"query": "BTC"}).json()["label"] == "safe"
