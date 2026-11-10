from conftest import login, qa_login, run


def test_whatif_anonymous(client):
    r = client.post("/api/whatif", json={"monthly_inr": 5000, "coin": "BTC", "years": 5})
    assert r.status_code == 200
    d = r.json()
    assert d["invested_inr"] == 5000 * 60 and d["value_inr"] > 0
    assert len(d["series"]) == 61 and d["worst"]["start"] and "peak" in d["worst"]["note"]
    assert d["worst"]["return_pct"] <= d["return_pct"] + 1e-9 or d["worst"]["start"] == d["series"][0]["month"]


def test_xray_link_message_coin_contract(client):
    r = client.post("/api/xray", json={"query": "kucoin-support-login.xyz/verify"}).json()
    assert r["kind"] == "link" and r["label"] in ("risky", "likely_scam")
    assert any("kucoin" in f["title"].lower() for f in r["red_flags"])
    client.cookies.clear()
    r = client.post("/api/xray", json={"query": "Join our VIP Telegram group, guaranteed 3% daily returns, send USDT to start today only"}).json()
    assert r["kind"] == "message" and r["label"] == "likely_scam"
    client.cookies.clear()
    r = client.post("/api/xray", json={"query": "https://www.binance.com/en"}).json()
    assert r["label"] == "safe" and any("Official" in g for g in r["green_flags"])


def test_xray_coin_and_contract_logged_in(client):
    qa_login(client)
    r = client.post("/api/xray", json={"query": "Bitcoin"}).json()
    assert r["kind"] == "coin" and r["coin"]["symbol"] == "BTC" and r["label"] == "safe" and r["what_it_does"]
    r = client.post("/api/xray", json={"query": "0x1234567890abcdef1234567890abcdef12345678"}).json()
    assert r["kind"] == "coin" and r["label"] in ("risky", "likely_scam") and r["red_flags"]
    r = client.post("/api/xray", json={"query": "NOTACOINXYZ"}).json()
    assert r["label"] != "safe"
    h = client.get("/api/xray/history").json()["items"]
    assert len(h) == 3


def test_anon_xray_one_a_day(client):
    assert client.post("/api/xray", json={"query": "ETH"}).status_code == 200
    r = client.post("/api/xray", json={"query": "ETH"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit" and r.json()["detail"]["signup"] is True


def test_public_pulse(client):
    d = client.get("/api/public/pulse").json()
    assert {c["symbol"] for c in d["coins"]} >= {"BTC", "ETH"}
    assert 0 <= d["cycle"]["position_pct"] <= 100 and d["cycle"]["phase"] and d["fear_greed"]["label"]


def test_verdicts_details_by_plan(seeded_client):
    c = seeded_client
    d = c.get("/api/verdicts/today").json()
    assert len(d["coins"]) == 10 and d["coins"][0]["bull"] is None
    assert any(v["changed_from"] for v in d["coins"])
    qa_login(c, plan="lite")
    d = c.get("/api/verdicts/today").json()
    assert d["coins"][0]["bull"] and d["coins"][0]["chair"]
    coin = c.get("/api/verdicts/coin/BTC").json()
    assert coin["verdict"]["symbol"] == "BTC" and coin["history"]


def test_forecast_debate_metered(client):
    qa_login(client, plan="lite")
    f = client.post("/api/verdicts/forecast", json={"symbol": "BTC", "horizon_days": 7}).json()
    assert len(f["path"]) == 7 and f["low_usd"] < f["expected_price_usd"] < f["high_usd"] and f["model"] == "statistical"
    assert f["usage"] == {"used": 1, "limit": 10, "period": "month"}
    d = client.post("/api/verdicts/debate", json={"symbol": "ETH"}).json()
    assert len(d["bull"]) == 3 and len(d["bear"]) == 3 and d["chair"]["verdict"] in ("Bullish", "Neutral", "Bearish")


def test_watchlist_and_verdict_change_alert(client, mdb):
    out = qa_login(client, plan="lite")
    assert client.post("/api/watchlist/btc").json()["symbols"] == ["BTC"]
    import asyncio
    from datetime import timedelta
    from growth.clock import utcnow, IST
    from jobs.registry import Ctx
    from features.verdicts import job_daily
    now = utcnow()
    run(job_daily(Ctx(mdb, now)))
    day = now.astimezone(IST).date().isoformat()
    v = run(mdb.verdicts.find_one({"_id": f"{day}:BTC"}))
    other = "Bullish" if v["verdict"] != "Bullish" else "Bearish"
    run(mdb.verdicts.update_one({"_id": v["_id"]}, {"$set": {"verdict": other, "date": (now - timedelta(days=1)).astimezone(IST).date().isoformat()},
                                 }))
    run(mdb.verdicts.delete_many({"date": day}))
    run(job_daily(Ctx(mdb, now)))
    inbox = client.get("/api/inbox").json()
    assert inbox["unread"] >= 1 and inbox["items"][0]["kind"] == "verdict_changed"
    client.post("/api/inbox/read-all")
    assert client.get("/api/inbox").json()["unread"] == 0
    assert client.delete("/api/watchlist/BTC").json()["symbols"] == []


def test_monday_picks(seeded_client):
    qa_login(seeded_client, plan="lite")
    d = seeded_client.get("/api/picks/monday").json()
    assert d["published"] and len(d["picks"]) == 2 and d["picks"][0]["change_pct"] is not None
