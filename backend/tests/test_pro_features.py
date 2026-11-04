from datetime import timedelta

from conftest import qa_login, run

from growth.clock import utcnow
from jobs.registry import Ctx

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def test_ask_answers_from_kb_and_refuses_picks(seeded_client):
    c = seeded_client
    qa_login(c)
    r = c.post("/api/ask", json={"question": "Why should I do a SIP in crypto?"}).json()
    assert r["answer"] and r["sources"] and not r["refused"] and r["thread_id"]
    r2 = c.post("/api/ask", json={"question": "Should I buy SOL now?", "thread_id": r["thread_id"]}).json()
    assert r2["refused"] and r2["thread_id"] == r["thread_id"]
    th = c.get(f"/api/ask/threads/{r['thread_id']}").json()
    assert len(th["messages"]) == 4
    assert c.get("/api/ask/threads").json()["items"][0]["id"] == r["thread_id"]


def test_coach_and_crash_job(client, mdb):
    qa_login(client)
    client.post("/api/plan", json={"goal_name": "1 BTC", "target_inr": 8_000_000, "lump_sum_inr": 100000,
                                   "monthly_inr": 10000, "years": 6, "risk": "aggressive"})
    co = client.get("/api/ask/coach").json()
    assert co["goal"]["name"] == "1 BTC" and co["crash"] is None
    import market
    from crypto.exchanges.fake import FakeExchange  # noqa: F401
    real_price = run(market.price("BTC"))

    async def low(_sym):
        return real_price * 0.6
    import features.ask as ask
    orig = ask.market.price
    ask.market.price = low
    try:
        res = run(ask.job_crash(Ctx(mdb, utcnow())))
    finally:
        ask.market.price = orig
    assert res["level"] == 40 and res["alerts"] >= 1
    co = client.get("/api/ask/coach").json()
    assert co["crash"]["active"] and co["crash"]["level"] == 40
    assert any(i["kind"] == "crash" for i in client.get("/api/inbox").json()["items"])


def test_baskets_practice_invest_and_change_alert(seeded_client, mdb):
    c = seeded_client
    qa_login(c)
    items = c.get("/api/baskets").json()["items"]
    core = next(b for b in items if b["name"].startswith("Bitcoin"))
    assert core["min_inr"] == 2000
    assert c.post(f"/api/baskets/{core['id']}/practice", json={"amount_inr": 1500}).status_code == 400
    paper = c.post(f"/api/baskets/{core['id']}/practice", json={"amount_inr": 10000}).json()
    assert {p["symbol"] for p in paper["positions"]} == {"BTC", "ETH"}
    c.post("/api/autopilot/link", json={"venue": "kucoin", "api_key": "goodkey1234", "api_secret": "secret12345",
                                        "passphrase": "pp"})
    r = c.post(f"/api/baskets/{core['id']}/invest", json={"venue": "kucoin", "amount_inr": 10000}).json()
    assert [o["status"] for o in r["orders"]] == ["filled", "filled"] and r["total_inr"] == 10000
    short = c.post(f"/api/baskets/{core['id']}/invest", json={"venue": "kucoin", "amount_inr": 5_000_000})
    assert short.status_code == 409 and short.json()["detail"]["code"] == "short_usdt"
    ap = c.post(f"/api/baskets/{core['id']}/autopilot", json={"venue": "kucoin", "amount_inr": 4000}).json()
    assert ap["kind"] == "basket" and ap["basket_name"] == core["name"]
    # admin changes the basket → holder alerted
    qa_login(c, role="admin")
    upd = c.put(f"/api/admin/baskets/{core['id']}", json={"name": core["name"], "coins": [{"symbol": "BTC", "weight_pct": 100}]})
    assert upd.status_code == 200 and "Removed ETH" in upd.json()["change_note"]
    bad = c.post("/api/admin/baskets", json={"name": "X", "coins": [{"symbol": "BTC", "weight_pct": 50}]})
    assert bad.status_code == 400
    holder = run(mdb.users.find_one({"phone": "+919000000012"}))
    assert run(mdb.inbox.count_documents({"user_id": str(holder["_id"]), "kind": "basket_change"})) == 1


def test_radar_calendar_p2p_news(seeded_client):
    c = seeded_client
    qa_login(c)
    r = c.get("/api/radar").json()
    kinds = {i["kind"] for i in r["items"]}
    assert kinds == {"new_listing", "trending"} and all(i["xray"]["label"] for i in r["items"])
    cal = c.get("/api/calendar?days=60").json()["items"]
    assert len(cal) >= 5 and cal[-1]["kind"] == "halving"
    p = c.get("/api/p2p?amount_inr=5000").json()
    assert {v["venue"] for v in p["venues"]} == {"binance", "kucoin"} and p["tips"]
    assert all(o["safety"] in ("high", "medium", "low") for v in p["venues"] for o in v["offers"])
    n = c.get("/api/news").json()["items"]
    assert len(n) == 6 and n[0]["what_it_means"]
    chk = c.post("/api/news/check", json={"text": "This coin will 100x, guaranteed! Presale ends tonight"}).json()
    assert chk["verdict"] == "hype"


def test_calendar_yours_flag(seeded_client):
    c = seeded_client
    qa_login(c)
    c.post("/api/watchlist/SUI")
    cal = c.get("/api/calendar").json()["items"]
    assert any(e["yours"] for e in cal if "SUI" in e["coins"])


def test_chart_reader(client):
    qa_login(client, plan="lite")
    r = client.post("/api/chart", files={"file": ("c.png", PNG, "image/png")}, data={"symbol": "btc"})
    assert r.status_code == 200 and r.json()["trend"] in ("up", "down", "sideways") and r.json()["usage"]["used"] == 1
    bad = client.post("/api/chart", files={"file": ("c.txt", b"hello", "text/plain")})
    assert bad.status_code == 400
    assert client.get("/api/me/plan").json()["limits"]["chart"]["used"] == 1     # refunded


def test_airdrops(seeded_client):
    c = seeded_client
    qa_login(c, plan="lite")
    items = c.get("/api/airdrops").json()["items"]
    assert items[0]["status"] == "live" and items[-1]["status"] == "ended"
    a = items[0]
    out = c.post(f"/api/airdrops/{a['id']}/steps/{a['steps'][0]['id']}", json={"done": True}).json()
    assert out["done_steps"] == [a["steps"][0]["id"]]
    out = c.post(f"/api/airdrops/{a['id']}/steps/{a['steps'][0]['id']}", json={"done": False}).json()
    assert out["done_steps"] == []
