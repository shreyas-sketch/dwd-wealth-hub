"""10 Nov review, round 3: usage period, Paper Money coins, atomic allowances, Autopilot re-checks the plan,
no admin promotion by email, webhook de-duplication, private API docs."""
import asyncio
import hashlib
import hmac
import json
from datetime import timedelta

from conftest import qa_login, run


# ---------------------------------------------------------------- usage line says "today" for logged-out X-Ray ----
def test_anon_xray_usage_is_per_day_and_member_usage_per_month(client):
    r = client.post("/api/xray", json={"query": "BTC"}).json()
    assert r["usage"]["period"] == "day"
    lim = client.post("/api/xray", json={"query": "ETH"}).json()["detail"]
    assert lim["code"] == "limit" and lim["period"] == "day"
    qa_login(client, plan="lite")
    assert client.post("/api/xray", json={"query": "SOL"}).json()["usage"]["period"] == "month"


# ---------------------------------------------------------------- Paper Money lists every tradable coin ----
def test_paper_sends_full_coin_list(client):
    qa_login(client, plan="lite")
    from features.paper import TRADABLE_ORDER
    d = client.get("/api/paper").json()
    assert d["tradable"] == list(TRADABLE_ORDER) and len(d["tradable"]) > 4 and "BNB" in d["tradable"]


# ---------------------------------------------------------------- allowance can't be over-used at the same moment ----
async def test_consume_is_atomic_under_concurrency(mdb):
    import plans
    user = {"_id": "u1"}

    async def one():
        try:
            return (await plans.consume(mdb, user, "xray", "free"))["used"]
        except Exception as e:  # noqa: BLE001
            return getattr(e, "status_code", e)
    out = await asyncio.gather(*(one() for _ in range(10)))
    assert sorted(x for x in out if isinstance(x, int) and x < 100) == [1, 2, 3] and out.count(402) == 7

    async def anon():
        try:
            return (await plans.anon_consume(mdb, "a:x", "xray", 2))["used"]
        except Exception as e:  # noqa: BLE001
            return getattr(e, "status_code", e)
    out = await asyncio.gather(*(anon() for _ in range(6)))
    assert out.count(402) == 4
    assert (await plans.anon_consume(mdb, "a:y", "xray", 1))["used"] == 1
    try:
        await plans.anon_consume(mdb, "a:z", "xray", 0)
        assert False, "a 0 allowance must refuse"
    except Exception as e:  # noqa: BLE001
        assert getattr(e, "status_code", None) == 402


# ---------------------------------------------------------------- Autopilot re-checks the plan before buying ----
def test_autopilot_pauses_plans_the_account_no_longer_allows(client, mdb):
    from features.autopilot import job_buys
    from growth.clock import utcnow
    from jobs.registry import Ctx
    me = qa_login(client)                                   # ₹5,000 trial
    client.post("/api/autopilot/link", json={"venue": "binance", "api_key": "goodkey1234", "api_secret": "secret12345"})
    eth = client.post("/api/autopilot/plan", json={"venue": "binance", "coin": "ETH", "amount_inr": 3000,
                                                   "frequency": "weekly"}).json()
    from bson import ObjectId
    uid = me["user"]["id"]
    run(mdb.users.update_one({"_id": ObjectId(uid)}, {"$set": {"trial_ends_at": utcnow() - timedelta(minutes=1)}}))
    run(mdb.dca_plans.update_many({}, {"$set": {"next_at": utcnow() - timedelta(minutes=1)}}))
    res = run(job_buys(Ctx(mdb, utcnow())))
    assert res["bought"] == 0 and res["paused"] == 1
    p = run(mdb.dca_plans.find_one({"_id": eth["id"]}))
    assert p["status"] == "paused" and "no longer includes" in p["last_error"]
    assert run(mdb.dca_buys.count_documents({})) == 0


def test_autopilot_pauses_for_revoked_account(client, mdb):
    from features.autopilot import job_buys
    from growth.clock import utcnow
    from jobs.registry import Ctx
    from bson import ObjectId
    me = qa_login(client, plan="lite")
    client.post("/api/autopilot/link", json={"venue": "binance", "api_key": "goodkey1234", "api_secret": "secret12345"})
    client.post("/api/autopilot/plan", json={"venue": "binance", "coin": "BTC", "amount_inr": 2000})
    run(mdb.users.update_one({"_id": ObjectId(me["user"]["id"])}, {"$set": {"status": "revoked"}}))
    run(mdb.dca_plans.update_many({}, {"$set": {"next_at": utcnow() - timedelta(minutes=1)}}))
    res = run(job_buys(Ctx(mdb, utcnow())))
    assert res["paused"] == 1 and run(mdb.dca_buys.count_documents({})) == 0


# ---------------------------------------------------------------- seed_admin never promotes a member ----
async def test_seed_admin_does_not_promote_existing_member(mdb, monkeypatch):
    from auth import seed_admin
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-strong-password-123")
    await mdb.users.insert_one({"email": "boss@example.com", "role": "user", "phone": "+919811111111"})
    await seed_admin(mdb)
    u = await mdb.users.find_one({"email": "boss@example.com"})
    assert u["role"] == "user" and "password_hash" not in u


# ---------------------------------------------------------------- the same payment webhook runs once ----
def test_webhook_duplicate_is_ignored(client, mdb):
    qa_login(client, plan="free")
    co = client.post("/api/billing/checkout", json={"plan": "pro"}).json()
    from billing.razorpay_client import FakeRazorpay
    body = json.dumps(FakeRazorpay().charge_event(co["subscription_id"], 590000)).encode()
    h = {"X-Razorpay-Signature": hmac.new(b"fake_webhook_secret", body, hashlib.sha256).hexdigest(),
         "X-Razorpay-Event-Id": "evt_123"}
    assert client.post("/api/billing/razorpay/webhook", content=body, headers=h).json() == {"ok": True}
    assert client.post("/api/billing/razorpay/webhook", content=body, headers=h).json()["duplicate"] is True
    assert run(mdb.events.count_documents({"name": "payment_captured"})) == 1


# ---------------------------------------------------------------- API docs are off in production ----
def test_api_docs_hidden_outside_qa(mdb, monkeypatch):
    from fastapi.testclient import TestClient

    import dataclasses

    import core.settings as cs
    import server
    monkeypatch.setattr(cs, "settings", dataclasses.replace(cs.settings, qa_mode=False))
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)
    with TestClient(server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)) as c:
        assert c.get("/api/docs").status_code == 404 and c.get("/api/openapi.json").status_code == 404
    monkeypatch.setenv("ENABLE_API_DOCS", "true")
    with TestClient(server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)) as c:
        assert c.get("/api/docs").status_code == 200
