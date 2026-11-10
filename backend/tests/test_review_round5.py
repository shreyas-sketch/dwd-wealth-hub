"""10 Nov full QA pass: security headers, Paper Money plan warning, Ask knows the app's tax facts."""
from datetime import timedelta

from conftest import qa_login, run


def test_security_headers_on_api_and_pages(client):
    for path in ("/api/health", "/api/verdicts/today", "/api/nope"):
        h = client.get(path).headers
        assert h["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "strict-origin-when-cross-origin"


def test_hsts_outside_qa(mdb, monkeypatch):
    import dataclasses

    from fastapi.testclient import TestClient

    import core.settings as cs
    import server
    monkeypatch.setattr(cs, "settings", dataclasses.replace(cs.settings, qa_mode=False))
    with TestClient(server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)) as c:
        assert c.get("/api/health").headers["strict-transport-security"].startswith("max-age=31536000")


def test_manual_trade_outside_plan_is_not_plan_drift(client, mdb):
    qa_login(client, plan="lite")
    plan = client.post("/api/plan", json={"goal_name": "House", "target_inr": 1000000, "years": 5, "risk": "moderate",
                                          "monthly_inr": 5000}).json()
    pid = plan.get("id") or plan.get("plan", {}).get("id")
    assert client.post("/api/paper/start", json={"plan_id": pid}).status_code == 200
    assert client.post("/api/paper/trade", json={"symbol": "DOGE", "side": "buy", "amount_inr": 2000}).status_code == 200
    assert client.get("/api/paper").json()["plan_drift"] is None          # the plan didn't change
    run(mdb.crypto_plans.update_one({"_id": pid}, {"$set": {"allocation": [{"symbol": "BTC", "pct": 70},
                                                                             {"symbol": "USDT", "pct": 30}]}}))
    d = client.get("/api/paper").json()["plan_drift"]
    assert d and "DOGE" in d["not_in_plan"]                                # it did now
    client.post("/api/paper/rebalance")
    assert client.get("/api/paper").json()["plan_drift"] is None


async def test_ask_knows_tax_facts():
    from features.ask import APP_FACTS, fake_answer
    out = fake_answer("How much tax do I pay on crypto profit? And TDS?", [], False)
    assert "30%" in out["answer"] and "1% TDS" in out["answer"] and out["answer"] == APP_FACTS
