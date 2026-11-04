from datetime import timedelta

from conftest import login, qa_login, run

from growth.clock import IST, utcnow


def test_admin_guard(client):
    assert client.get("/api/admin/pulse").status_code == 401
    qa_login(client)
    assert client.get("/api/admin/pulse").status_code == 403


def test_pulse_users_grant_trial(client, mdb):
    login(client, utm={"src": "webinar"})
    client.post("/api/auth/logout")
    qa_login(client, role="admin")
    p = client.get("/api/admin/pulse").json()
    assert p["kpis"]["users_total"] >= 1 and p["kpis"]["trial_active"] >= 1
    assert any(s["source"] == "webinar" for s in p["by_source"]) and len(p["signups_by_day"]) == 14
    users = client.get("/api/admin/users?q=98765").json()
    assert users["total"] == 1
    uid = users["items"][0]["id"]
    d = client.post(f"/api/admin/users/{uid}/trial", json={"days": 0}).json()
    assert d["plan"]["plan"] == "free"
    d = client.post(f"/api/admin/users/{uid}/grant", json={"plan": "lite", "months": 2}).json()
    assert d["plan"]["plan"] == "lite" and d["grants"]
    assert client.get("/api/admin/users?plan=lite").json()["total"] == 1
    d = client.post(f"/api/admin/users/{uid}/grant", json={"plan": "free", "months": 0}).json()
    assert d["plan"]["plan"] == "free"
    d = client.post(f"/api/admin/users/{uid}/status", json={"status": "revoked"}).json()
    assert d["user"]["status"] == "revoked"
    assert client.get(f"/api/admin/users/{uid}").json()["events"]


def test_flags_settings_vendors(client):
    qa_login(client, role="admin")
    items = client.get("/api/admin/flags").json()["items"]
    assert any(f["key"] == "RADAR" for f in items)
    out = client.post("/api/admin/flags", json={"key": "RADAR", "on": False}).json()["items"]
    assert next(f for f in out if f["key"] == "RADAR")["on"] is False
    s = client.post("/api/admin/settings", json={"trial_days": 5, "scenario_rates": {"bad": -10, "average": 12, "good": 30}}).json()
    assert s["trial_days"] == 5 and s["scenario_rates"]["bad"] == -10
    assert {v["name"] for v in client.get("/api/admin/vendors").json()["vendors"]} >= {"razorpay", "anthropic", "market"}


def test_webinar_report_and_csv(client):
    for ph in ("9876500011", "9876500012"):
        login(client, phone=ph, utm={"src": "webinar"})
        client.post("/api/xray", json={"query": "BTC"})
        client.post("/api/auth/logout")
    qa_login(client, role="admin")
    today = utcnow().astimezone(IST).date().isoformat()
    w = client.get(f"/api/admin/webinar?start={today}&end={today}").json()
    assert w["signups"] == 2 and w["day3_list_count"] == 2
    assert any(f["feature"] == "Coin X-Ray" and f["users"] == 2 for f in w["feature_usage"])
    csv = client.get(f"/api/admin/webinar/day3.csv?start={today}&end={today}")
    assert csv.status_code == 200 and csv.text.count("\n") == 3 and "+919876500011" in csv.text


def test_content_crud(seeded_client):
    c = seeded_client
    qa_login(c, role="admin")
    a = c.post("/api/admin/airdrops", json={"name": "Test drop", "coin": "sol", "steps": [{"text": "Do a thing"}]}).json()
    assert a["coin"] == "SOL" and a["xray"]["label"] and a["steps"][0]["id"]
    assert c.put(f"/api/admin/airdrops/{a['id']}", json={"name": "Test drop 2", "status": "ended"}).json()["status"] == "ended"
    assert c.delete(f"/api/admin/airdrops/{a['id']}").json()["ok"]
    ev = c.post("/api/admin/events", json={"date": "2026-12-01", "title": "Test event", "kind": "macro", "coins": ["btc"]}).json()
    assert ev["coins"] == ["BTC"]
    assert c.delete(f"/api/admin/events/{ev['id']}").json()["ok"]
    sug = c.get("/api/admin/picks/suggest").json()["picks"]
    assert len(sug) == 2
    pk = c.post("/api/admin/picks", json={"published": True, "picks": [{"symbol": s["symbol"], "reasoning": "Because"} for s in sug]}).json()
    assert pk["published"] and pk["picks"][0]["price_at_pick_usd"]
    notes = c.post("/api/admin/crash-notes", json={"notes": [{"level": 25, "note": "Stay calm."}]}).json()["notes"]
    assert any(n["level"] == 25 and n["note"] == "Stay calm." for n in notes)
    vtt = b"WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nStaking means locking coins to earn rewards.\n\n2\n00:00:04.000 --> 00:00:06.000\nUnstaking can take days.\n"
    up = c.post("/api/admin/kb", files={"file": ("staking.vtt", vtt, "text/vtt")}, data={"title": "Staking"}).json()
    assert up["chunks"] == 1 and up["words"] == 11
    assert any(k["title"] == "Staking" for k in c.get("/api/admin/kb").json()["items"])
    assert c.post("/api/admin/kb", files={"file": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 400
    assert c.delete(f"/api/admin/kb/{up['id']}").json()["ok"]
    etf = c.post("/api/admin/etf-flows", json={"date": "2026-11-01", "net_usd_m": 120.5}).json()["items"]
    assert any(e["date"] == "2026-11-01" for e in etf)


def test_jobs_listing_and_run(client, mdb):
    qa_login(client, role="admin")
    items = client.get("/api/admin/jobs").json()["items"]
    assert {j["name"] for j in items} >= {"verdicts_daily", "autopilot_buys", "radar_scan", "news_fetch"}
    for name in ("verdicts_daily", "radar_scan", "news_fetch", "paper_snapshot", "events_alerts", "crash_coach",
                 "exchange_reverify", "autopilot_buys", "radar_digest"):
        r = client.post(f"/api/admin/jobs/{name}/run").json()
        assert r["ok"], (name, r)
    assert client.get("/api/admin/jobs").json()["items"][0]["last"]["ok"]


def test_tick_due_and_ingest_key(client, mdb, monkeypatch):
    assert client.post("/api/jobs/tick").status_code == 401
    monkeypatch.setenv("INGEST_KEY", "k" * 20)
    r = client.post("/api/jobs/tick", headers={"X-Ingest-Key": "k" * 20})
    assert r.status_code == 200 and "verdicts_daily" in r.json()["ran"]
    from jobs import registry
    assert "verdicts_daily" not in run(registry.due(mdb))


def test_event_alerts_day_before(seeded_client, mdb):
    c = seeded_client
    qa_login(c)
    from features.calendar import job_alerts
    from jobs.registry import Ctx
    res = run(job_alerts(Ctx(mdb, utcnow())))
    assert res["events"] >= 1 and res["sent"] >= 1
