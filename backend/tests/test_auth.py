from datetime import timedelta

from conftest import login, run

from growth.clock import utcnow


def test_otp_signup_creates_account_with_trial(client, mdb):
    out = login(client, utm={"src": "webinar"})
    assert out["is_new"] is True
    assert out["user"]["phone"] == "+919876543210" and out["user"]["name"] == "Asha"
    me = client.get("/api/auth/me").json()
    assert me["plan"]["plan"] == "pro" and me["plan"]["source"] == "trial"
    u = run(mdb.users.find_one({"phone": "+919876543210"}))
    assert u["acquisition"]["source"] == "webinar"
    assert u["trial_ends_at"] is not None


def test_second_login_is_not_new(client, mdb):
    login(client)
    client.post("/api/auth/logout")
    run(mdb.otp_challenges.delete_many({}))      # skip the 30 s resend cooldown
    assert client.get("/api/auth/me").status_code == 401
    out = login(client)
    assert out["is_new"] is False


def test_request_reports_new_or_existing(client):
    r = client.post("/api/auth/otp/request", json={"phone": "9123456780"}).json()
    assert r["is_new"] is True and r["sent_to"].startswith("+91 91")


def test_bad_phone_and_wrong_code(client):
    assert client.post("/api/auth/otp/request", json={"phone": "12345"}).status_code == 400
    d = client.post("/api/auth/otp/request", json={"phone": "9876500000"}).json()
    wrong = "111111" if d["dev_code"] != "111111" else "222222"
    r = client.post("/api/auth/otp/verify", json={"challenge_id": d["challenge_id"], "phone": "9876500000", "code": wrong})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wrong_code"


def test_qa_bypass_code(client):
    d = client.post("/api/auth/otp/request", json={"phone": "9876500001"}).json()
    r = client.post("/api/auth/otp/verify", json={"challenge_id": d["challenge_id"], "phone": "9876500001", "code": "000000"})
    assert r.status_code == 200


def test_admin_phone_gets_admin(client):
    out = login(client, phone="9000000002")
    assert out["user"]["role"] == "admin"


def test_staff_login(mdb, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "staff@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret-pass")
    import server
    from fastapi.testclient import TestClient
    app = server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)
    with TestClient(app) as c:
        assert c.post("/api/auth/staff/login", json={"email": "staff@example.com", "password": "nope"}).status_code == 401
        r = c.post("/api/auth/staff/login", json={"email": "STAFF@example.com", "password": "s3cret-pass"})
        assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
        assert c.get("/api/admin/pulse").status_code == 200


def test_revoked_user_blocked(client, mdb):
    login(client)
    run(mdb.users.update_one({"phone": "+919876543210"}, {"$set": {"status": "revoked"}}))
    assert client.get("/api/auth/me").status_code == 403


def test_profile_update(client):
    login(client)
    r = client.patch("/api/auth/profile", json={"name": "Asha K", "email": "asha@example.com"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "asha@example.com"


def test_refresh(client):
    login(client)
    assert client.post("/api/auth/refresh").status_code == 200
