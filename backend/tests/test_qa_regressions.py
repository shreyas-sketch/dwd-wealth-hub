"""Regression tests for bugs found in the QA pass (docs/QA_REPORT.md). One test per bug, named after it."""
import re
from datetime import timedelta

from conftest import qa_login, run

from growth.clock import utcnow
from jobs.registry import Ctx


# ---- Coin X-Ray -------------------------------------------------------------------------------------------
def test_xray_lookalike_domain_is_not_called_official(client):
    qa_login(client)
    d = client.post("/api/xray", json={"query": "blnance.com"}).json()
    assert d["label"] != "safe" and any("binance" in f["title"] for f in d["red_flags"])
    for typo in ("kuc0in.com", "wazrix.com", "metamsk.io"):
        assert client.post("/api/xray", json={"query": typo}).json()["label"] != "safe", typo
    unknown = client.post("/api/xray", json={"query": "randomsite.com"}).json()
    assert "official" not in unknown["headline"].lower()
    real = client.post("/api/xray", json={"query": "https://www.binance.com/en"}).json()
    assert real["label"] == "safe" and "official" in real["headline"].lower()
    assert client.post("/api/xray", json={"query": "opensea.io"}).json()["label"] == "safe"


def test_xray_brand_names_are_spelled_properly(client):
    qa_login(client)
    d = client.post("/api/xray", json={"query": "kucoin-support.help"}).json()
    assert any("The real KuCoin site" in f["detail"] for f in d["red_flags"])


def test_xray_blank_query_is_refused_without_using_a_check(client):
    qa_login(client, plan="free")
    r = client.post("/api/xray", json={"query": "    "})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "empty"
    assert client.get("/api/me/plan").json()["limits"]["xray"]["used"] == 0


def test_xray_finds_dollar_and_coin_suffix_forms(client):
    qa_login(client)
    for q in ("$PEPE", "pepe coin"):
        d = client.post("/api/xray", json={"query": q}).json()
        assert d["coin"] and d["coin"]["symbol"] == "PEPE", q


# ---- Admin settings -----------------------------------------------------------------------------------------
def test_admin_settings_bad_number_is_400_not_500(client):
    qa_login(client, role="admin")
    for body in ({"trial_days": "abc"}, {"crash_levels": ["x"]}, {"scenario_rates": {"bad": "x"}}):
        r = client.post("/api/admin/settings", json=body)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_setting", body
    assert client.get("/api/admin/settings").json()["trial_days"] == 3


# ---- My Crypto Plan ---------------------------------------------------------------------------------------
def test_pro_at_plan_cap_is_not_told_to_upgrade(client):
    qa_login(client)                                      # pro trial: 3 plans
    body = {"goal_name": "G", "target_inr": 100000, "lump_sum_inr": 0, "monthly_inr": 1000, "years": 3, "risk": "safe"}
    for _ in range(3):
        assert client.post("/api/plan", json=body).status_code == 200
    r = client.post("/api/plan", json=body)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "plans_full"
    assert "₹5,000 plan holds" not in r.json()["detail"]["msg"]


def test_lite_plan_cap_still_offers_upgrade(client):
    qa_login(client, plan="lite")
    body = {"goal_name": "G", "target_inr": 100000, "lump_sum_inr": 0, "monthly_inr": 1000, "years": 3, "risk": "safe"}
    client.post("/api/plan", json=body)
    r = client.post("/api/plan", json=body)
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "pro"


# ---- Autopilot ----------------------------------------------------------------------------------------------
def test_lite_autopilot_eth_message_explains_the_limit(client):
    qa_login(client, plan="lite")
    client.post("/api/autopilot/link", json={"venue": "binance", "api_key": "goodkey1234", "api_secret": "secret12345"})
    r = client.post("/api/autopilot/plan", json={"venue": "binance", "coin": "ETH", "amount_inr": 2000})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert "Bitcoin once a month" in r.json()["detail"]["msg"]


def test_fake_key_containing_withdraw_is_refused(client):
    qa_login(client)
    r = client.post("/api/autopilot/link", json={"venue": "binance", "api_key": "mykey_withdraw_1", "api_secret": "secret12345"})
    assert r.status_code == 400 and r.json()["detail"]["rejected_reason"] == "withdrawal_scope"


def test_kucoin_spelled_properly_in_messages(client):
    qa_login(client)
    r = client.get("/api/autopilot/balance/kucoin")
    assert "KuCoin" in r.json()["detail"]["msg"]


# ---- Airdrops / events (admin content) ------------------------------------------------------------------------
def test_airdrop_xray_checks_the_link_too(client):
    qa_login(client, role="admin")
    a = client.post("/api/admin/airdrops", json={"name": "Drop", "coin": "SUI", "link": "https://kucoin-support.help/claim"}).json()
    assert a["xray"]["label"] == "likely_scam"
    ok = client.post("/api/admin/airdrops", json={"name": "Drop 2", "coin": "SUI", "link": "https://www.kucoin.com/gempool"}).json()
    assert ok["xray"]["label"] == "safe"


def test_airdrop_deadline_and_event_date_must_be_real_dates(client):
    qa_login(client, role="admin")
    assert client.post("/api/admin/airdrops", json={"name": "T", "deadline": "tomorrow"}).status_code == 422
    assert client.post("/api/admin/airdrops", json={"name": "T", "deadline": ""}).json()["deadline"] is None
    r = client.post("/api/admin/events", json={"date": "2026-02-30", "title": "x", "kind": "macro"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_date"


# ---- Billing ------------------------------------------------------------------------------------------------
def _buy(client, plan):
    co = client.post("/api/billing/checkout", json={"plan": plan}).json()
    return client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]}).json(), co["subscription_id"]


def test_upgrade_stops_the_old_subscription_renewing(client, mdb):
    qa_login(client, plan="free")
    _, lite_id = _buy(client, "lite")
    out, pro_id = _buy(client, "pro")
    assert out["plan"]["plan"] == "pro"
    old = run(mdb.subscriptions.find_one({"_id": lite_id}))
    new = run(mdb.subscriptions.find_one({"_id": pro_id}))
    assert old["cancel_at_cycle_end"] is True and old["replaced_by"] == pro_id
    assert not new.get("cancel_at_cycle_end")
    assert client.get("/api/me/plan").json()["cancelling"] is False


def test_cancel_marks_plan_cancelling_and_cannot_repeat(client):
    qa_login(client, plan="free")
    _buy(client, "lite")
    r = client.post("/api/billing/cancel").json()
    assert r["status"] == "cancels_at_period_end" and r["access_until"]
    info = client.get("/api/me/plan").json()
    assert info["plan"] == "lite" and info["cancelling"] is True
    assert client.post("/api/billing/cancel").status_code == 404


# ---- Limits wording ------------------------------------------------------------------------------------------
def test_limit_message_names_the_thing_counted(client, mdb):
    u = qa_login(client, plan="lite")
    from growth.clock import ist_month_key
    run(mdb.usage.update_one({"_id": f"{u['user']['id']}:{ist_month_key()}"}, {"$set": {"debate": 10}}, upsert=True))
    r = client.post("/api/verdicts/debate", json={"symbol": "BTC"})
    assert r.status_code == 402 and "10 Bull vs Bear debates" in r.json()["detail"]["msg"]
    assert "checks" not in r.json()["detail"]["msg"]


# ---- What If ----------------------------------------------------------------------------------------------------
def test_whatif_worst_note_reads_cleanly(client):
    d = client.post("/api/whatif", json={"monthly_inr": 5000, "coin": "BTC", "years": 3}).json()
    note = d["worst"]["note"]
    assert "peak" in note and "3 years" in note and not note.startswith("Started")


# ---- Crash coach --------------------------------------------------------------------------------------------------
def test_crash_alert_has_a_note_for_a_level_without_one(client, mdb):
    qa_login(client)
    import appsettings
    run(appsettings.update(mdb, {"crash_levels": [5]}))
    import market
    run(market.history("BTC", 31))
    from features.ask import job_crash
    res = run(job_crash(Ctx(mdb, utcnow())))
    if res.get("level") is None:                          # fake market not 5% below its high today: force it
        run(mdb.crash_state.delete_many({}))
        import features.ask as ask_f

        async def hist(*a, **k):
            return [("d", 100.0)] * 31

        async def price(*a, **k):
            return 90.0
        old_h, old_p = ask_f.market.history, ask_f.market.price
        ask_f.market.history, ask_f.market.price = hist, price
        try:
            res = run(job_crash(Ctx(mdb, utcnow())))
        finally:
            ask_f.market.history, ask_f.market.price = old_h, old_p
    assert res["level"] == 5
    st = run(mdb.crash_state.find_one({"_id": "btc"}))
    assert st["note"] and "5%" in st["note"]


# ---- Admin guard: every /api/admin route --------------------------------------------------------------------------
def test_every_admin_route_refuses_non_admins(app, client):
    routes = sorted({(m, r.path) for r in app.routes if getattr(r, "path", "").startswith("/api/admin")
                     for m in r.methods if m in ("GET", "POST", "PUT", "DELETE")})
    assert len(routes) >= 30

    def walk(expected):
        bad = []
        for m, p in routes:
            path = re.sub(r"\{[^}]+\}", "x", p.replace("{user_id}", "0123456789abcdef01234567"))
            r = client.request(m, path, json={})
            if r.status_code != expected:
                bad.append((m, path, r.status_code))
        return bad

    assert walk(401) == []                                  # logged out
    for who in ({"plan": "free"}, {"plan": "lite"}, {}):     # members, including the ₹5,000 trial
        qa_login(client, **who)
        assert walk(403) == [], who
        client.post("/api/auth/logout")


def test_revoked_member_is_blocked_on_next_request(client):
    member = qa_login(client)
    uid = member["user"]["id"]
    member_cookies = dict(client.cookies)
    client.cookies.clear()
    qa_login(client, role="admin")
    assert client.post(f"/api/admin/users/{uid}/status", json={"status": "revoked"}).status_code == 200
    client.cookies.clear()
    for k, v in member_cookies.items():
        client.cookies.set(k, v)
    r = client.get("/api/auth/me")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "revoked"
    assert client.post("/api/auth/refresh").status_code == 403


def test_trial_ending_downgrades_access(client, mdb):
    u = qa_login(client, phone="9876512345")
    assert client.get("/api/baskets").status_code == 200
    from bson import ObjectId
    run(mdb.users.update_one({"_id": ObjectId(u["user"]["id"])}, {"$set": {"trial_ends_at": utcnow() - timedelta(minutes=1)}}))
    assert client.get("/api/me/plan").json()["plan"] == "free"
    r = client.get("/api/baskets")
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "pro"
