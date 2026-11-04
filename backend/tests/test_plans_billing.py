import hashlib
import hmac
import json
from datetime import timedelta

from conftest import login, qa_login, run

from growth.clock import utcnow


def test_trial_then_free_after_expiry(client, mdb):
    login(client)
    assert client.get("/api/me/plan").json()["plan"] == "pro"
    run(mdb.users.update_one({"phone": "+919876543210"}, {"$set": {"trial_ends_at": utcnow() - timedelta(minutes=1)}}))
    info = client.get("/api/me/plan").json()
    assert info["plan"] == "free" and info["features"]["ask"] is False and info["limits"]["xray"]["limit"] == 3


def test_free_xray_limit_then_402(client):
    qa_login(client, plan="free")
    for _ in range(3):
        assert client.post("/api/xray", json={"query": "BTC"}).status_code == 200
    r = client.post("/api/xray", json={"query": "BTC"})
    assert r.status_code == 402
    d = r.json()["detail"]
    assert d["code"] == "limit" and d["plan_needed"] == "lite" and d["used"] == 3


def test_lite_locked_out_of_pro_features(client):
    qa_login(client, plan="lite")
    r = client.post("/api/ask", json={"question": "What is DCA?"})
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "pro"
    for path in ("/api/baskets", "/api/radar", "/api/calendar", "/api/p2p", "/api/news"):
        assert client.get(path).status_code == 403, path
    assert client.get("/api/airdrops").status_code == 200


def test_free_locked_out_of_lite_features(client):
    qa_login(client, plan="free")
    r = client.post("/api/verdicts/forecast", json={"symbol": "BTC", "horizon_days": 7})
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "lite"
    assert client.get("/api/airdrops").status_code == 403


def test_catalog_public(client):
    r = client.get("/api/plans/catalog").json()
    assert [p["id"] for p in r["plans"]] == ["free", "lite", "pro"] and r["trial_days"] == 3


def test_fake_checkout_verify_activates(client):
    qa_login(client, plan="free")
    co = client.post("/api/billing/checkout", json={"plan": "lite"}).json()
    assert co["mode"] == "fake" and co["amount_inr"] == 2360 and co["price_inr"] == 2000 and co["gst_inr"] == 360 and co["subscription_id"].startswith("sub_")
    r = client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"], "payment_id": "x", "signature": "y"})
    assert r.status_code == 200 and r.json()["plan"]["plan"] == "lite" and r.json()["plan"]["source"] == "paid"
    c = client.post("/api/billing/cancel").json()
    assert c["status"] == "cancels_at_period_end"
    assert client.get("/api/me/plan").json()["plan"] == "lite"     # access until the paid month ends


def test_webhook_signature_and_charge(client, mdb):
    qa_login(client, plan="free")
    co = client.post("/api/billing/checkout", json={"plan": "pro"}).json()
    from billing.razorpay_client import FakeRazorpay
    fake = FakeRazorpay()
    ev = fake.charge_event(co["subscription_id"], 500000)
    body = json.dumps(ev).encode()
    assert client.post("/api/billing/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": "bad"}).status_code == 400
    sig = hmac.new(b"fake_webhook_secret", body, hashlib.sha256).hexdigest()
    assert client.post("/api/billing/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": sig}).status_code == 200
    info = client.get("/api/me/plan").json()
    assert info["plan"] == "pro" and info["source"] == "paid"
    ev2 = {"event": "subscription.halted", "payload": {"subscription": {"entity": {"id": co["subscription_id"]}}}}
    b2 = json.dumps(ev2).encode()
    client.post("/api/billing/razorpay/webhook", content=b2,
                headers={"X-Razorpay-Signature": hmac.new(b"fake_webhook_secret", b2, hashlib.sha256).hexdigest()})
    assert client.get("/api/me/plan").json()["plan"] == "free"


def test_usage_resets_by_month_key(client, mdb):
    qa_login(client, plan="lite")
    client.post("/api/xray", json={"query": "ETH"})
    info = client.get("/api/me/plan").json()
    assert info["limits"]["xray"] == {"used": 1, "limit": 30}
