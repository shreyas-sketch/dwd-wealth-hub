"""Admin report counts (QA findings 3 Nov): grants count as their plan, admins and revoked accounts stay out."""
from conftest import login, qa_login

from growth.clock import IST, utcnow


def _today():
    return utcnow().astimezone(IST).date().isoformat()


def test_reports_count_grants_and_skip_admins_and_revoked(client):
    login(client, phone="9876500001", name="Granted")
    client.post("/api/auth/logout")
    login(client, phone="9876500002", name="Revoked")
    client.post("/api/auth/logout")
    login(client, phone="9876500003", name="Plain")
    client.post("/api/auth/logout")
    qa_login(client, role="admin")
    ids = {u["name"]: u["id"] for u in client.get("/api/admin/users").json()["items"]}
    client.post(f"/api/admin/users/{ids['Granted']}/grant", json={"plan": "pro", "months": 1})
    client.post(f"/api/admin/users/{ids['Revoked']}/status", json={"status": "revoked"})
    for name in ("Granted", "Revoked", "Plain"):
        client.post(f"/api/admin/users/{ids[name]}/trial", json={"days": 0})

    p = client.get("/api/admin/pulse").json()
    mix = {m["plan"]: m["count"] for m in p["plan_mix"]}
    assert mix["pro"] >= 1 and p["kpis"]["granted_active"] == 1 and p["kpis"]["pro_active"] == 0

    t = _today()
    w = client.get(f"/api/admin/webinar?start={t}&end={t}").json()
    assert w["signups"] == 2                     # revoked and admin left out
    assert w["day3_list_count"] == 1             # only "Plain": "Granted" has a plan
    csv = client.get(f"/api/admin/webinar/day3.csv?start={t}&end={t}").text
    assert "Plain" in csv and "Granted" not in csv and "Revoked" not in csv and "Admin" not in csv
    assert client.get("/api/admin/webinar?start=2026-01-01&end=2026-12-31").status_code == 400   # > 3 months
