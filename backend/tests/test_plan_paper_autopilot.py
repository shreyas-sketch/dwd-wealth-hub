from datetime import timedelta

from conftest import qa_login, run

from growth.clock import utcnow
from jobs.registry import Ctx

PLAN = {"goal_name": "Kids' education", "target_inr": 2_500_000, "lump_sum_inr": 50000, "monthly_inr": 5000,
        "years": 5, "risk": "moderate"}


def test_plan_scenarios_and_limits(client):
    qa_login(client, plan="lite")
    p = client.post("/api/plan", json=PLAN).json()
    assert [a["symbol"] for a in p["allocation"]] == ["BTC", "ETH", "SOL", "XRP"]
    assert p["invested_total_inr"] == 50000 + 5000 * 60
    sc = {s["key"]: s for s in p["scenarios"]}
    assert sc["bad"]["end_value_inr"] == 350000 and sc["good"]["end_value_inr"] > sc["average"]["end_value_inr"] > 350000
    assert len(p["yearly"]) == 5
    r = client.post("/api/plan", json=PLAN)
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "pro"
    assert client.get("/api/plan").json()["max"] == 1


def test_paper_start_trade_and_free_lock(client):
    qa_login(client, plan="free")
    p = client.post("/api/plan", json=PLAN).json()
    paper = client.post("/api/paper/start", json={"plan_id": p["id"]}).json()
    assert round(paper["value_inr"]) in range(99_000, 101_000) and len(paper["positions"]) == 4 and not paper["can_trade"]
    r = client.post("/api/paper/trade", json={"symbol": "BTC", "side": "sell", "amount_inr": 1000})
    assert r.status_code == 403
    plans_ = client.get("/api/plan").json()["plans"]
    assert plans_[0]["goal_progress"]["source"] == "paper" and plans_[0]["paper_started"]


def test_paper_trades_lite(client, mdb):
    qa_login(client, plan="lite")
    p = client.post("/api/plan", json={**PLAN, "risk": "safe"}).json()
    client.post("/api/paper/start", json={"plan_id": p["id"]})
    before = client.get("/api/paper").json()
    assert before["cash_inr"] == 19000.0                 # ₹10,000 kept back + the USDT share of ₹90,000
    after = client.post("/api/paper/trade", json={"symbol": "SOL", "side": "buy", "amount_inr": 5000}).json()
    assert any(x["symbol"] == "SOL" for x in after["positions"]) and after["cash_inr"] == 14000.0
    sold = client.post("/api/paper/trade", json={"symbol": "SOL", "side": "sell", "amount_inr": 100000}).json()
    assert not any(x["symbol"] == "SOL" for x in sold["positions"])
    assert client.post("/api/paper/trade", json={"symbol": "FAKECOIN", "side": "buy", "amount_inr": 10}).status_code == 400
    from features.paper import job_snapshot
    assert run(job_snapshot(Ctx(mdb, utcnow())))["snapshots"] == 1
    assert client.post("/api/paper/reset").json()["started_at"] is None


def test_autopilot_link_rules(client):
    qa_login(client, plan="lite")
    bad = client.post("/api/autopilot/link", json={"venue": "binance", "api_key": "withdraw-key-123", "api_secret": "secret12345"})
    assert bad.status_code == 400 and "Withdrawals" in bad.json()["detail"]["msg"]
    nopass = client.post("/api/autopilot/link", json={"venue": "kucoin", "api_key": "goodkey123", "api_secret": "secret12345"})
    assert nopass.status_code == 400 and nopass.json()["detail"]["code"] == "passphrase"
    ok = client.post("/api/autopilot/link", json={"venue": "binance", "api_key": "goodkey1234", "api_secret": "secret12345"}).json()
    assert ok["linked"] and ok["key_tail"] == "••••1234" and "api_secret" not in str(ok)
    st = client.get("/api/autopilot").json()
    assert st["allowed"] == {"coins": ["BTC"], "frequencies": ["monthly"]}
    assert client.post("/api/autopilot/plan", json={"venue": "binance", "coin": "ETH", "amount_inr": 2000}).status_code == 403
    assert client.post("/api/autopilot/plan", json={"venue": "binance", "coin": "BTC", "amount_inr": 2000,
                                                    "frequency": "weekly"}).status_code == 403
    p = client.post("/api/autopilot/plan", json={"venue": "binance", "coin": "BTC", "amount_inr": 2000, "day": 5}).json()
    assert p["status"] == "active" and p["next_at"]
    assert client.post(f"/api/autopilot/plan/{p['id']}/pause").json()["status"] == "paused"
    assert client.post(f"/api/autopilot/plan/{p['id']}/resume").json()["status"] == "active"
    bal = client.get("/api/autopilot/balance/binance").json()
    assert bal["usdt"] == 5000.0 and bal["inr_est"] > 0


def test_autopilot_job_buys_and_short_usdt(client, mdb):
    qa_login(client)                            # pro trial
    client.post("/api/autopilot/link", json={"venue": "binance", "api_key": "goodkey1234", "api_secret": "secret12345"})
    p = client.post("/api/autopilot/plan", json={"venue": "binance", "coin": "ETH", "amount_inr": 5000, "frequency": "weekly"}).json()
    big = client.post("/api/autopilot/plan", json={"venue": "binance", "coin": "BTC", "amount_inr": 900000}).json()
    run(mdb.dca_plans.update_many({}, {"$set": {"next_at": utcnow() - timedelta(minutes=1)}}))
    from features.autopilot import job_buys
    res = run(job_buys(Ctx(mdb, utcnow())))
    assert {k: res[k] for k in ("bought", "failed", "due")} == {"bought": 1, "failed": 1, "due": 2}
    assert res["next_due_at"]                   # both plans moved to their next slot
    st = client.get("/api/autopilot").json()
    by = {x["id"]: x for x in st["plans"]}
    assert by[p["id"]]["buys"] == 1 and by[p["id"]]["invested_inr"] == 5000
    assert "Not enough USDT" in by[big["id"]]["last_error"]
    kinds = [i["title"] for i in client.get("/api/inbox").json()["items"]]
    assert any("bought" in k for k in kinds) and any("couldn't buy" in k for k in kinds)
    port = client.get("/api/portfolio").json()
    assert port["linked"] == ["binance"] and port["total_inr"] > 0
    assert client.delete("/api/autopilot/link/binance").json()["ok"]


def test_reverify_job(client, mdb):
    qa_login(client, plan="lite")
    client.post("/api/autopilot/link", json={"venue": "binance", "api_key": "goodkey1234", "api_secret": "secret12345"})
    from features.autopilot import job_reverify
    assert run(job_reverify(Ctx(mdb, utcnow())))["verified"] == 1
