"""Shared fixtures. Tests never touch a real Mongo or the network: mongomock-motor + fake vendors."""
import os

os.environ["APP_LAZY"] = "1"
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200")
os.environ.setdefault("DB_NAME", "coinzeye_test")
os.environ.setdefault("JWT_SECRET", "test-secret-please-change-0123456789")
os.environ["APP_ENV"] = "test"
os.environ["QA_MODE"] = "true"
os.environ["COOKIE_SECURE"] = "false"
os.environ["INPROCESS_SCHEDULER"] = "false"
os.environ["ADMIN_PHONES"] = "+919000000002"

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *a, **k: False

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402


@pytest.fixture
def mdb():
    return AsyncMongoMockClient()["coinzeye_test"]


@pytest.fixture(autouse=True)
def _reset_caches():
    import appsettings
    import market
    from core import flags
    from crypto.exchanges.fake import FakeExchange
    appsettings.reset_cache()
    market.clear_cache()
    flags._cache["values"] = {}
    FakeExchange.reset()
    from features import p2p
    p2p._cache.clear()
    from features import ask
    ask.reset_kb_cache()
    import llm
    llm.reset_pools()            # semaphores bind to an event loop; each test gets fresh ones
    from market import live
    live.CG_BUCKET.reset()
    live._ids.clear()
    from market import twelvedata as td
    td.reset_state()
    from accounts import otp_service
    for b in otp_service.BREAKERS.values():
        b.success()
    yield


@pytest.fixture
def app(mdb):
    import server
    return server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_client(mdb):
    import server
    a = server.create_app(mdb, start_jobs=False, seed=True, serve_spa=False)
    with TestClient(a) as c:
        yield c


def login(client, phone="9876543210", name="Asha", utm=None):
    r = client.post("/api/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    d = r.json()
    r = client.post("/api/auth/otp/verify", json={"challenge_id": d["challenge_id"], "phone": phone,
                                                  "code": d["dev_code"], "name": name, "utm": utm or {}})
    assert r.status_code == 200, r.text
    return r.json()


def qa_login(client, **body):
    r = client.post("/api/qa/login", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def run(coro):
    """Run a coroutine against mongomock from a sync test."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
