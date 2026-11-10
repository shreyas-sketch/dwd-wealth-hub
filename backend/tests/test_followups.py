"""Regression tests for the items the 3 Nov QA / load-test reports left open ("Found but not fixed").

Each block names the report item it covers.
"""
import itertools

from conftest import qa_login


# ---------------------------------------------------------------- debate evidence matches its point ----
def _ind(ema20, ema50, chg30, rsi, dd, vol):
    return {"price": 100.0, "rsi14": rsi, "ema20": ema20, "ema50": ema50, "chg7": 0.0, "chg30": chg30,
            "vol30_ann": vol, "drawdown90": dd, "daily_vol": 0.03, "drift": 0.0}


def test_rule_signals_always_three_per_side_with_matching_evidence():
    from features.verdicts import rule_verdict
    combos = itertools.product((110, 90), (-12.0, 0.0, 12.0), (20.0, 45.0, 60.0, 80.0), (-40.0, 0.0), (40.0, 120.0))
    for ema20, chg30, rsi, dd, vol in combos:
        ind = _ind(ema20, 100, chg30, rsi, dd, vol)
        v, conf, bull, bear = rule_verdict(ind, rank=3)
        assert len(bull) == 3 and len(bear) == 3, (ind, bull, bear)
        assert v in ("Bullish", "Neutral", "Bearish") and 50 <= conf <= 85
        for sig in bull + bear:
            # the evidence for an RSI point is the RSI, for a 30-day point the 30-day change, …
            if sig.point.startswith("RSI"):
                assert sig.evidence == f"RSI {rsi}"
            if "over 30 days" in sig.point:
                assert sig.evidence == f"30-day change {chg30}%"
            if "trend" in sig.point and "average" in sig.point:
                assert sig.evidence.startswith("20-day avg")
            if "90-day high" in sig.point:
                assert "90-day high" in sig.evidence
        assert len({s.point for s in bull}) == 3 and len({s.point for s in bear}) == 3


def test_debate_endpoint_points_and_evidence_pair_up(client):
    qa_login(client, plan="lite")
    for sym in ("BTC", "ETH", "SOL", "XRP"):
        d = client.post("/api/verdicts/debate", json={"symbol": sym}).json()
        assert len(d["bull"]) == 3 and len(d["bear"]) == 3
        for p in d["bull"] + d["bear"]:
            if p["point"].startswith("RSI"):
                assert p["evidence"].startswith("RSI")


def test_live_debate_reply_is_validated():
    from features.verdicts import _valid_debate
    good = {"bull": [{"point": "a", "evidence": "x"}] * 3, "bear": [{"point": "b", "evidence": "y"}] * 3,
            "chair": {"verdict": "Neutral", "confidence": 50, "call": "c"}}
    assert _valid_debate(good) is good
    assert _valid_debate({**good, "bear": good["bear"][:2]}) is None
    assert _valid_debate({**good, "bull": [{"point": "a"}] * 3}) is None
    assert _valid_debate({**good, "chair": {"verdict": "Buy"}}) is None
    assert _valid_debate("nope") is None


# ---------------------------------------------------------------- settings: reject, don't clip ----
def test_settings_out_of_range_is_rejected_with_field_errors(client):
    qa_login(client, role="admin")
    cases = [({"trial_days": 31}, "trial_days", "between 0 days and 30 days"),
             ({"trial_days": 2.5}, "trial_days", "whole number"),
             ({"anon_xray_per_day": -1}, "anon_xray_per_day", "between 0 and 20"),
             ({"crash_levels": [3, 20]}, "crash_levels", "between 5% and 90%"),
             ({"crash_levels": [20, 20]}, "crash_levels", "only once"),
             ({"crash_levels": []}, "crash_levels", "at least one"),
             ({"scenario_rates": {"bad": 0, "average": 150, "good": 35}}, "scenario_rates.average", "between -50% and 100%"),
             ({"scenario_rates": {"bad": 20, "average": 10, "good": 35}}, "scenario_rates", "go up")]
    for body, field, words in cases:
        r = client.post("/api/admin/settings", json=body)
        assert r.status_code == 400, body
        d = r.json()["detail"]
        assert d["code"] == "bad_setting" and field in d["errors"] and words in d["errors"][field], (body, d)
    s = client.get("/api/admin/settings").json()
    assert s["trial_days"] == 3 and s["crash_levels"] == [20, 30, 40]     # nothing was clipped or saved


def test_settings_one_bad_field_saves_nothing(client):
    qa_login(client, role="admin")
    r = client.post("/api/admin/settings", json={"trial_days": 7, "anon_xray_per_day": 99})
    assert r.status_code == 400 and set(r.json()["detail"]["errors"]) == {"anon_xray_per_day"}
    assert client.get("/api/admin/settings").json()["trial_days"] == 3


def test_settings_valid_values_and_spec(client):
    qa_login(client, role="admin")
    s = client.post("/api/admin/settings", json={"trial_days": 30, "crash_levels": [40, 5, 25],
                                                 "scenario_rates": {"bad": -5, "average": 10.5, "good": 30}}).json()
    assert s["trial_days"] == 30 and s["crash_levels"] == [5, 25, 40] and s["scenario_rates"]["average"] == 10.5
    spec = client.get("/api/admin/settings/spec").json()
    assert spec["fields"]["trial_days"] == {"label": "Trial days", "min": 0, "max": 30, "integer": True, "unit": "days"}
    assert spec["max_crash_levels"] == 6


# ---------------------------------------------------------------- airdrop ticks follow the step ----
def _airdrop(client, steps, aid=None):
    body = {"name": "Drop", "status": "live", "steps": steps}
    r = client.put(f"/api/admin/airdrops/{aid}", json=body) if aid else client.post("/api/admin/airdrops", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_airdrop_ticks_follow_step_when_admin_reorders(client):
    qa_login(client, role="admin")
    a = _airdrop(client, [{"text": "Create a wallet"}, {"text": "Bridge funds"}, {"text": "Make a swap"}])
    ids = {s["text"]: s["id"] for s in a["steps"]}
    assert len(set(ids.values())) == 3
    # an admin is pro, so they can tick too
    client.post(f"/api/airdrops/{a['id']}/steps/{ids['Bridge funds']}", json={"done": True})
    # reorder with ids sent back, and insert a new first step without an id
    steps = [{"text": "Read the rules"}, {"id": ids["Make a swap"], "text": "Make a swap"},
             {"id": ids["Bridge funds"], "text": "Bridge funds"}, {"id": ids["Create a wallet"], "text": "Create a wallet"}]
    b = _airdrop(client, steps, a["id"])
    assert [s["id"] for s in b["steps"][1:]] == [ids["Make a swap"], ids["Bridge funds"], ids["Create a wallet"]]
    assert b["steps"][0]["id"] not in ids.values()
    mine = next(x for x in client.get("/api/airdrops").json()["items"] if x["id"] == a["id"])
    assert mine["done_steps"] == [ids["Bridge funds"]]


def test_airdrop_text_only_save_matches_by_text_and_drops_removed_ticks(client, mdb):
    qa_login(client, role="admin")
    a = _airdrop(client, [{"text": "One"}, {"text": "Two"}, {"text": "Three"}])
    ids = {s["text"]: s["id"] for s in a["steps"]}
    client.post(f"/api/airdrops/{a['id']}/steps/{ids['One']}", json={"done": True})
    client.post(f"/api/airdrops/{a['id']}/steps/{ids['Three']}", json={"done": True})
    # text-only client, reversed, "One" removed
    b = _airdrop(client, [{"text": "three "}, {"text": "Two"}], a["id"])
    assert [s["id"] for s in b["steps"]] == [ids["Three"], ids["Two"]]
    mine = next(x for x in client.get("/api/airdrops").json()["items"] if x["id"] == a["id"])
    assert mine["done_steps"] == [ids["Three"]]
    import asyncio
    prog = asyncio.get_event_loop().run_until_complete(mdb.airdrop_progress.find_one({"airdrop_id": a["id"]}))
    assert prog["done_steps"] == [ids["Three"]]


def test_reconcile_steps_never_duplicates_ids():
    from features.airdrops import StepDef, reconcile_steps
    old = [{"id": "a", "text": "Same"}, {"id": "b", "text": "Same"}]
    out = reconcile_steps([StepDef(id="a", text="Same"), StepDef(id="a", text="Same"), StepDef(text="Same")], old)
    assert len({s["id"] for s in out}) == 3 and out[0]["id"] == "a" and out[1]["id"] == "b"


# ---------------------------------------------------------------- Admin › Jobs: sentences, not JSON ----
def test_job_summaries():
    from jobs.summaries import describe
    assert describe("autopilot_buys", {"bought": 3, "failed": 1, "due": 4, "next_due_at": None}) == "3 plans bought, 1 failed (of 4 due)."
    s = describe("autopilot_buys", {"bought": 0, "failed": 0, "due": 0, "next_due_at": "2026-11-05T04:30:00+00:00"})
    assert s == "No plans were due. Next buy: 5 Nov 10:00 IST."
    assert describe("autopilot_buys", {"bought": 0, "failed": 0, "due": 0, "next_due_at": None}) == "No plans were due. No active plans."
    assert describe("news_fetch", {"added": 1}) == "1 new story summarised."
    assert describe("news_fetch", {"added": 5}) == "5 new stories summarised."
    assert describe("radar_scan", {"status": "off"}).startswith("Skipped: this feature is switched off")
    assert describe("crash_coach", {"drawdown_pct": 4.2, "level": None}) == "BTC is 4.2% below its 30-day high; no crash level reached."
    assert describe("events_alerts", {"sent": 0}) == "No events tomorrow."
    assert describe("x", None, "ValueError: boom") == "Failed: ValueError: boom"
    assert describe("unknown_job", {"a_b": 1, "rows": [1, 2]}) == "a b: 1, rows: 2 items"
    assert describe("verdicts_daily", {"coins": 10, "changed": 1, "date": "2026-11-04"}) == "10 coins rated for 4 Nov; 1 verdict changed."
    assert describe("verdicts_daily", {"coins": "bad"}).startswith("0 coins")   # odd shapes never raise


def test_admin_jobs_listing_and_run_return_summaries(client):
    qa_login(client, role="admin")
    r = client.post("/api/admin/jobs/autopilot_buys/run").json()
    assert r["ok"] is True and r["summary"].startswith("No plans were due") and isinstance(r["result"], dict)
    item = next(i for i in client.get("/api/admin/jobs").json()["items"] if i["name"] == "autopilot_buys")
    assert item["last"]["summary"] == r["summary"] and item["last"]["ok"] is True


# ---------------------------------------------------------------- session probe: no 401 on public pages ----
def test_session_probe_logged_out_is_200(client):
    r = client.get("/api/auth/session")
    assert r.status_code == 200 and r.json() == {"user": None, "plan": None, "reason": None}
    assert r.headers["cache-control"] == "no-store"
    assert client.get("/api/auth/me").status_code == 401          # /me contract unchanged


def test_session_probe_logged_in_and_renews_from_refresh_cookie(client):
    from conftest import login
    login(client)
    d = client.get("/api/auth/session").json()
    assert d["user"]["phone"] == "+919876543210" and d["plan"]["plan"] and d["reason"] is None
    client.cookies.delete("access_token")                        # access expired, refresh still good
    r = client.get("/api/auth/session")
    assert r.json()["user"]["phone"] == "+919876543210"
    assert "access_token" in r.headers.get("set-cookie", "")


def test_session_probe_bad_cookie_and_revoked(client, mdb):
    client.cookies.set("access_token", "garbage")
    r = client.get("/api/auth/session")
    assert r.status_code == 200 and r.json()["reason"] == "expired"
    client.cookies.clear()
    from conftest import login
    out = login(client, phone="9876500099")
    import asyncio
    from bson import ObjectId
    asyncio.get_event_loop().run_until_complete(
        mdb.users.update_one({"_id": ObjectId(out["user"]["id"])}, {"$set": {"status": "revoked"}}))
    r = client.get("/api/auth/session")
    assert r.status_code == 200 and r.json() == {"user": None, "plan": None, "reason": "revoked"}


# ---------------------------------------------------------------- AI bulkheads (load test hard burst) ----
def test_vision_burst_does_not_starve_fast_pool(monkeypatch):
    import asyncio

    import llm
    monkeypatch.setenv("LLM_MAX_CONCURRENCY_VISION", "2")
    monkeypatch.setenv("LLM_MAX_CONCURRENCY_FAST", "2")
    monkeypatch.setenv("LLM_QUEUE_WAIT_S_VISION", "0.05")
    monkeypatch.setenv("LLM_QUEUE_WAIT_S_FAST", "0.05")
    gate = asyncio.Event()

    async def slow():
        await gate.wait()
        return "v"

    async def quick():
        return "f"

    async def go():
        vision = [asyncio.ensure_future(llm._guarded(slow, "chart", "vision")) for _ in range(3)]
        await asyncio.sleep(0.01)
        fast = await llm._guarded(quick, "xray", "fast")       # vision pool is full; fast still has room
        busy = await asyncio.gather(*vision[2:], return_exceptions=True)
        gate.set()
        done = await asyncio.gather(*vision[:2])
        return fast, busy[0], done
    fast, busy, done = asyncio.new_event_loop().run_until_complete(go())
    assert fast == "f" and done == ["v", "v"]
    assert isinstance(busy, llm.AIBusy) and busy.retry_after == 20
    stats = {p["pool"]: p for p in llm.pool_stats()}
    assert stats["vision"]["rejected"] == 1 and stats["vision"]["size"] == 2 and stats["fast"]["rejected"] == 0


def test_queue_wait_defaults(monkeypatch):
    import llm
    monkeypatch.delenv("LLM_QUEUE_WAIT_S", raising=False)
    assert {p["pool"]: p["queue_wait_s"] for p in llm.pool_stats()} == {"fast": 15.0, "strong": 15.0, "vision": 45.0}
    monkeypatch.setenv("LLM_QUEUE_WAIT_S", "20")                # legacy knob still moves fast/strong
    llm.reset_pools()
    assert {p["pool"]: p["queue_wait_s"] for p in llm.pool_stats()} == {"fast": 20.0, "strong": 20.0, "vision": 45.0}


def test_chart_busy_is_503_with_retry_after_and_refund(client, monkeypatch):
    import llm
    from features import chart_vision

    async def busy(**kw):
        raise llm.AIBusy("busy", retry_after=20)
    monkeypatch.setattr(llm, "complete_json", busy)
    qa_login(client, plan="lite")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = client.post("/api/chart", files={"file": ("c.png", png, "image/png")})
    assert r.status_code == 503 and r.headers["retry-after"] == "20"
    assert r.json()["detail"]["code"] == "unavailable" and r.json()["detail"]["retry_after"] == 20
    me = client.get("/api/auth/me").json()
    assert me["plan"]["limits"]["chart"]["used"] == 0                 # refunded
    assert chart_vision.MAX_BYTES == 5 * 1024 * 1024


# ---------------------------------------------------------------- market data under webinar load ----
class _CountingMarket:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def prices(self, syms):
        self.calls.append(list(syms))
        if self.fail:
            raise RuntimeError("upstream down")
        return {s: {"symbol": s, "price_usd": 1.0 + len(s)} for s in syms if s != "NOPE"}


async def test_prices_cached_per_coin_and_fetch_only_missing(monkeypatch):
    import market
    fake = _CountingMarket()
    monkeypatch.setattr(market, "provider", lambda: fake)
    market.clear_cache()
    assert set(await market.prices(["BTC", "ETH"])) == {"BTC", "ETH"}
    assert set(await market.prices(["ETH", "SOL", "usdt"])) == {"ETH", "SOL", "USDT"}
    assert set(await market.prices(["BTC", "SOL", "NOPE"])) == {"BTC", "SOL"}
    assert set(await market.prices(["NOPE"])) == set()                 # a miss is remembered too
    assert fake.calls == [["BTC", "ETH"], ["SOL"], ["NOPE"]]


async def test_prices_serve_stale_quote_when_upstream_fails(monkeypatch):
    import time

    import market
    fake = _CountingMarket()
    monkeypatch.setattr(market, "provider", lambda: fake)
    market.clear_cache()
    await market.prices(["BTC"])
    at, val = market._cache["px1:BTC"]
    market._cache["px1:BTC"] = (at - 120, val)                         # expired, but within 10× TTL
    market._cache.pop("px:BTC", None)
    fake.fail = True
    assert (await market.prices(["BTC"]))["BTC"]["price_usd"] == val["price_usd"]
    assert market._cache["px1:BTC"][0] < time.time() - 100             # stale value was not re-stamped as fresh


async def test_coingecko_budget_and_429_cool_down():
    import httpx
    import pytest

    from core.http import RateLimited, TokenBucket
    from market import live
    b = TokenBucket(60, 60, burst=2, name="t")
    await b.acquire(0)
    await b.acquire(0)
    with pytest.raises(RateLimited):
        await b.acquire(0)                                             # budget spent, no waiting allowed

    def handler(req):
        return httpx.Response(429, headers={"retry-after": "30"}, json={})
    lm = live.LiveMarket(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(RateLimited):
        await lm.top_coins(5)
    with pytest.raises(RateLimited):                                   # cooling down: not even sent
        await lm.top_coins(5)


async def test_coingecko_symbol_ids_are_cached():
    import httpx

    from market import live
    seen = []

    def handler(req):
        seen.append(req.url.path)
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"coins": [{"id": "zzz-coin", "symbol": "ZZZ"}]})
        return httpx.Response(200, json=[{"id": "zzz-coin", "symbol": "zzz", "name": "Z", "current_price": 2}])
    lm = live.LiveMarket(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await lm.prices(["ZZZ"])
    await lm.prices(["ZZZ"])
    assert sum(p.endswith("/search") for p in seen) == 1


# ---------------------------------------------------------------- OTP: skip a failing WhatsApp ----
async def test_otp_whatsapp_breaker_sends_by_sms_directly():
    from accounts import otp_service
    from accounts.otp_providers import Senders, SendResult

    class Wa:
        channel, name = "whatsapp", "aisensy"
        calls = 0

        async def send(self, phone, code, ttl):
            Wa.calls += 1
            return SendResult(False, "aisensy", "whatsapp", error="429 burst limit")

    class Sms:
        channel, name = "sms", "msg91"

        async def send(self, phone, code, ttl):
            return SendResult(True, "msg91", "sms", ref="x")
    s = Senders(whatsapp=Wa(), sms=Sms())
    for _ in range(5):                                                 # 5 failures in a row open the breaker
        res, fell = await otp_service._deliver(s, "+919000000001", "123456", "auto")
        assert res.ok and res.channel == "sms" and fell
    assert Wa.calls == 5 and otp_service.BREAKERS["whatsapp"].open
    res, fell = await otp_service._deliver(s, "+919000000001", "123456", "auto")
    assert res.ok and res.channel == "sms" and fell and Wa.calls == 5   # WhatsApp skipped
    await otp_service._deliver(s, "+919000000001", "123456", "whatsapp")
    assert Wa.calls == 6                                               # an explicit choice is still tried


def test_airdrop_create_keeps_supplied_ids(client):
    qa_login(client, role="admin")
    a = _airdrop(client, [{"id": "s1", "text": "One"}, {"id": "s2", "text": "Two"}])
    assert [s["id"] for s in a["steps"]] == ["s1", "s2"]
    b = _airdrop(client, [{"id": "s2", "text": "Two"}, {"id": "s1", "text": "One"}], a["id"])
    assert [(s["id"], s["text"]) for s in b["steps"]] == [("s2", "Two"), ("s1", "One")]


# ---------------------------------------------------------------- verdict hit rate ----
def test_judge_bands_and_wilson():
    from features.accuracy import judge, wilson
    assert judge("Bullish", 3.1, 7) is True and judge("Bullish", 2.9, 7) is False
    assert judge("Bearish", -6.5, 30) is True and judge("Bearish", -5.0, 30) is False
    assert judge("Neutral", 2.0, 7) is True and judge("Neutral", -3.5, 7) is False
    assert wilson(0, 0) == (None, None)
    lo, hi = wilson(6, 10)
    assert 30 < lo < 60 < hi < 85                      # 6 of 10 is compatible with anything from ~31% to ~83%


async def test_scoring_job_live_and_missed_days(mdb, monkeypatch):
    from datetime import timedelta

    import market
    from features import accuracy
    from growth.clock import IST, utcnow
    from jobs.registry import Ctx
    now = utcnow()
    today = now.astimezone(IST).date()
    d7 = (today - timedelta(days=7)).isoformat()                  # exactly 7 days ago → live price
    d9 = (today - timedelta(days=9)).isoformat()                  # missed → daily close on d9 + 7
    await mdb.verdicts.insert_many([
        {"_id": f"{d7}:BTC", "date": d7, "symbol": "BTC", "verdict": "Bullish", "confidence": 68, "price_usd": 100.0},
        {"_id": f"{d9}:ETH", "date": d9, "symbol": "ETH", "verdict": "Bearish", "confidence": 59, "price_usd": 50.0},
        {"_id": f"{d9}:SOL", "date": d9, "symbol": "SOL", "verdict": "Neutral", "confidence": 50}])   # no price: skipped

    async def prices(syms):
        return {"BTC": {"symbol": "BTC", "price_usd": 110.0}}

    async def history(sym, days):
        target = (today - timedelta(days=2)).isoformat()
        return [(target, 45.0)] if sym == "ETH" else []
    monkeypatch.setattr(market, "prices", prices)
    monkeypatch.setattr(market, "history", history)
    r = await accuracy.job_score(Ctx(mdb, now))
    assert r == {"scored_7d": 2, "scored_30d": 0, "skipped": 1}
    btc = await mdb.verdict_outcomes.find_one({"_id": f"{d7}:BTC:7"})
    eth = await mdb.verdict_outcomes.find_one({"_id": f"{d9}:ETH:7"})
    assert btc["return_pct"] == 10.0 and btc["correct"] is True and btc["end_basis"] == "live"
    assert eth["return_pct"] == -10.0 and eth["correct"] is True and eth["end_basis"] == "daily_close"
    assert (await accuracy.job_score(Ctx(mdb, now)))["scored_7d"] == 0          # already scored: not redone


async def test_summary_compares_with_chance(mdb):
    from datetime import timedelta

    from features import accuracy
    from growth.clock import IST, utcnow
    day = (utcnow().astimezone(IST).date() - timedelta(days=10)).isoformat()
    rows = []
    # 10 coin-weeks: 6 rose >3%, 4 fell >3%. Bullish was said 5 times and right 4 times.
    for i, (verdict, ret) in enumerate([("Bullish", 5)] * 4 + [("Bullish", -5)] + [("Bearish", 5)] * 2
                                       + [("Bearish", -5)] * 3):
        rows.append({"_id": f"{day}:C{i}:7", "date": day, "symbol": f"C{i}", "verdict": verdict, "confidence": 72 if i < 2 else 55,
                     "horizon": 7, "price_start": 1, "price_end": 1, "return_pct": ret,
                     "correct": accuracy.judge(verdict, ret, 7), "end_basis": "live", "scored_at": utcnow()})
    await mdb.verdict_outcomes.insert_many(rows)
    s = await accuracy.summary(mdb, 30)
    h7 = next(h for h in s["horizons"] if h["horizon_days"] == 7)
    bull = next(v for v in h7["by_verdict"] if v["verdict"] == "Bullish")
    bear = next(v for v in h7["by_verdict"] if v["verdict"] == "Bearish")
    assert h7["calls"] == 10 and h7["right"] == 7 and h7["enough_data"] is False
    assert bull["hit_rate_pct"] == 80.0 and bull["chance_pct"] == 60.0 and bull["edge_pts"] == 20.0
    assert bear["hit_rate_pct"] == 60.0 and bear["chance_pct"] == 40.0
    assert h7["spread_pct"] == round(3.0 - (-1.0), 2)                         # avg after Bullish minus after Bearish
    top = next(b for b in h7["by_confidence"] if b["bucket"] == "70% and up")
    assert top["calls"] == 2 and top["hit_rate_pct"] == 100.0
    assert next(h for h in s["horizons"] if h["horizon_days"] == 30)["calls"] == 0


def test_accuracy_endpoint_admin_only_and_job_listed(client):
    assert client.get("/api/admin/verdicts/accuracy").status_code == 401
    qa_login(client, plan="lite")
    assert client.get("/api/admin/verdicts/accuracy").status_code == 403
    qa_login(client, role="admin")
    d = client.get("/api/admin/verdicts/accuracy?days=30").json()
    assert d["days"] == 30 and [h["horizon_days"] for h in d["horizons"]] == [7, 30]
    r = client.post("/api/admin/jobs/verdict_scoring/run").json()
    assert r["ok"] is True and r["summary"].startswith("Scored 0 verdicts at 7 days")


# ---------------------------------------------------------------- WhatsApp-only OTP (AiSensy, no SMS) ----
def _wa_only_env(monkeypatch, campaign="hub_login_code_"):
    monkeypatch.setenv("OTP_PROVIDER_MODE", "live")
    monkeypatch.setenv("AISENSY_API_KEY", "test-key")
    monkeypatch.setenv("AISENSY_OTP_CAMPAIGN", campaign)
    monkeypatch.delenv("MSG91_AUTH_KEY", raising=False)
    monkeypatch.delenv("MSG91_OTP_TEMPLATE_ID", raising=False)


def test_whatsapp_used_when_it_is_the_only_channel_even_with_switch_off(monkeypatch):
    from accounts.otp_providers import build_senders
    from core import flags
    _wa_only_env(monkeypatch)
    monkeypatch.setattr(flags, "is_on", lambda key: False)            # Admin › Features › WhatsApp OTP is off
    s = build_senders()
    assert s.sms is None and s.whatsapp is not None and s.whatsapp.campaign == "hub_login_code_"


async def test_aisensy_payload_uses_campaign_and_code():
    import json

    import httpx
    from accounts.otp_providers import AiSensyWhatsApp
    seen = {}

    def h(req):
        seen.update(url=str(req.url), body=json.loads(req.content))
        return httpx.Response(200, json={"success": "true", "submitted_message_id": "m1"})
    wa = AiSensyWhatsApp("k", "hub_login_code_", httpx.AsyncClient(transport=httpx.MockTransport(h)))
    res = await wa.send("+919876543210", "482913", 10)
    b = seen["body"]
    assert res.ok and res.ref == "m1" and seen["url"] == "https://backend.aisensy.com/campaign/t1/api/v2"
    assert b["campaignName"] == "hub_login_code_" and b["destination"] == "919876543210"
    assert b["templateParams"] == ["482913"]
    assert b["buttons"] == [{"type": "button", "sub_type": "url", "index": 0, "parameters": [{"type": "text", "text": "482913"}]}]


async def test_sms_request_goes_by_whatsapp_when_sms_is_not_set_up():
    from accounts import otp_service
    from accounts.otp_providers import Senders, SendResult

    class Wa:
        channel, name = "whatsapp", "aisensy"
        ok = True

        async def send(self, phone, code, ttl):
            return SendResult(Wa.ok, "aisensy", "whatsapp", ref="x", error=None if Wa.ok else "HTTP 400")
    s = Senders(whatsapp=Wa(), sms=None)
    res, _ = await otp_service._deliver(s, "+919000000001", "123456", "sms")
    assert res.ok and res.channel == "whatsapp"


def test_otp_request_says_whether_sms_exists(client):
    r = client.post("/api/auth/otp/request", json={"phone": "9876500123"}).json()
    assert r["can_sms"] is True                                        # QA console sender offers both


async def test_failed_sends_do_not_use_up_the_code_allowance(mdb):
    from accounts import otp_service
    from accounts.otp_providers import Senders, SendResult
    from growth.clock import utcnow

    class Wa:
        channel, name = "whatsapp", "aisensy"
        ok = False

        async def send(self, phone, code, ttl):
            return SendResult(Wa.ok, "aisensy", "whatsapp", ref="m", error=None if Wa.ok else "HTTP 400: campaign not found")
    s = Senders(whatsapp=Wa(), sms=None)
    now = utcnow()
    for _ in range(6):                                  # six failures: more than the 5-codes-an-hour allowance
        try:
            await otp_service.request_otp(mdb, s, "+919000000009", now=now)
        except otp_service.OtpError as e:
            assert e.code == "send_failed"
    Wa.ok = True                                        # template fixed: the member can get a code straight away
    ch = await otp_service.request_otp(mdb, s, "+919000000009", now=now)
    assert ch.channel == "whatsapp"


async def test_failed_sends_have_their_own_brake(mdb):
    from accounts import otp_service
    from accounts.otp_providers import Senders, SendResult
    from growth.clock import utcnow

    class Wa:
        channel, name = "whatsapp", "aisensy"

        async def send(self, phone, code, ttl):
            return SendResult(False, "aisensy", "whatsapp", error="HTTP 400")
    s = Senders(whatsapp=Wa(), sms=None)
    now = utcnow()
    codes = []
    for _ in range(11):
        try:
            await otp_service.request_otp(mdb, s, "+919000000010", now=now)
        except otp_service.OtpError as e:
            codes.append(e.code)
    assert codes[:10] == ["send_failed"] * 10 and codes[10] == "send_failures"
