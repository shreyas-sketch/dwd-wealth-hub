"""Coinzeye load test (locust). Scenarios are picked with SCENARIO:

  spike    webinar QR moment: new visitors use the free tools, sign up by OTP and try the app once
  members  logged-in members (from scripts/seed_load.py) browsing with 3–10 s think time
  admin    an admin clicking through the reports over the full data set
  mixed    members + a slice of spike visitors + one admin (default)

    SCENARIO=spike locust -f scripts/loadtest/locustfile.py --host http://127.0.0.1:8000 \
        --headless -u 500 -r 9 -t 2m --csv /tmp/lt/spike

The app must run with QA_MODE=true (fake vendors; OTP 000000 accepted). Each simulated person sends its own
X-Forwarded-For so per-IP limits behave like real traffic (set SHARED_IP=1 to put everyone behind one IP,
like an Indian mobile carrier's CGNAT).
"""
from __future__ import annotations

import itertools
import os
from datetime import datetime, timedelta, timezone
import random
from pathlib import Path

import gevent
from locust import FastHttpUser, between, events, task
from locust.exception import StopUser

SCENARIO = os.environ.get("SCENARIO", "mixed")
MEMBERS = int(os.environ.get("MEMBERS", "10000"))         # seeded phones +9170000000xx
SHARED_IP = os.environ.get("SHARED_IP") == "1"
CHART = (Path(__file__).parent / "chart.png").read_bytes()
COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"]
XRAY_QUERIES = ["pepe", "bitcoin", "solana", "Double your USDT in 7 days, join our Telegram group",
                "https://kucoin-support-login.xyz", "dogecoin", "0x6982508145454ce325ddbe47a25d4ec3d2311933", "shiba inu"]

IST = timezone(timedelta(hours=5, minutes=30))
JOURNEYS = {"done": 0}
_seq = itertools.count(random.randint(0, 9_000_000))
_member = itertools.count(random.randint(0, MEMBERS))


def ip_for(n: int) -> str:
    return "100.64.0.1" if SHARED_IP else f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


class Base(FastHttpUser):
    abstract = True

    def on_start(self):
        self.n = next(_seq)
        self.h = {"X-Forwarded-For": ip_for(self.n), "Content-Type": "application/json"}

    def get(self, path, name=None):
        with self.client.get(path, headers=self.h, name=name or path, catch_response=True) as r:
            if r.status_code >= 500 or r.status_code == 0:
                r.failure(f"{r.status_code}")
            elif r.status_code in (401, 403, 402, 404, 409):
                r.success()                   # plan gates and limits are correct answers, not failures
            return r

    def post(self, path, body=None, name=None):
        with self.client.post(path, json=body or {}, headers=self.h, name=name or path, catch_response=True) as r:
            if r.status_code >= 500 or r.status_code == 0:
                r.failure(f"{r.status_code}")
            elif r.status_code == 429 and "/auth/otp" in path:
                r.failure("429 OTP limit")   # a person who can't get a code can't sign up: count it
            elif r.status_code == 402 and "(anon)" in (name or ""):
                r.failure("402 free X-Ray blocked")    # the public page's one free check was refused
            elif r.status_code in (400, 401, 402, 403, 404, 409, 429):
                r.success()
            return r

    def login(self, phone: str, name: str = "Load Test") -> bool:
        r = self.post("/api/auth/otp/request", {"phone": phone}, name="/api/auth/otp/request")
        if r.status_code != 200:
            return False
        cid = r.json().get("challenge_id")
        v = self.post("/api/auth/otp/verify", {"challenge_id": cid, "phone": phone, "code": "000000", "name": name,
                                               "utm": {"utm_source": "webinar", "utm_campaign": "load"}},
                      name="/api/auth/otp/verify")
        return v.status_code == 200


class WebinarVisitor(Base):
    """Scans the QR code, uses the free tools, signs up, tries the app once, then idles on the Zoom."""
    wait_time = between(1, 4)

    done = False

    @task
    def journey(self):
        if self.done:                         # one journey per person (like the real QR moment), then stay on Zoom
            gevent.sleep(30)
            return
        self.done = True
        self.get("/", name="/ (open page)")
        self.get("/api/public/pulse")
        self.get("/api/plans/catalog")
        self.get("/api/verdicts/today", name="/api/verdicts/today (anon)")
        self.post("/api/whatif", {"monthly_inr": random.choice([2000, 5000, 10000]), "coin": random.choice(["BTC", "ETH", "SOL"]),
                                  "years": random.choice([3, 5])})
        self.post("/api/xray", {"query": random.choice(XRAY_QUERIES)}, name="/api/xray (anon)")
        phone = f"+918{self.n % 1_000_000_000:09d}"
        if not self.login(phone, f"Visitor {self.n}"):
            raise StopUser()
        self.get("/api/auth/session")
        self.get("/api/verdicts/today")
        self.get("/api/pulse")
        self.get("/api/inbox")
        p = self.post("/api/plan", {"goal_name": "1 BTC", "target_inr": 5_000_000, "lump_sum_inr": 50_000,
                                    "monthly_inr": 5000, "years": 5, "risk": random.choice(["safe", "moderate", "aggressive"])})
        if p.status_code == 200:
            self.post("/api/paper/start", {"plan_id": p.json()["id"]})
        self.get("/api/paper")
        self.post("/api/xray", {"query": random.choice(XRAY_QUERIES)})
        self.post("/api/ask", {"question": random.choice(["What is DCA?", "How do I keep my coins safe?",
                                                          "What is a Bitcoin halving?"])})
        self.client.post("/api/chart", files={"file": ("chart.png", CHART, "image/png")},
                         headers={"X-Forwarded-For": self.h["X-Forwarded-For"]}, name="/api/chart")
        JOURNEYS["done"] += 1


class Member(Base):
    """A logged-in member (seeded 10k) using the app between Zoom sessions."""
    wait_time = between(3, 10)

    def on_start(self):
        super().on_start()
        i = next(_member) % MEMBERS
        self.phone = f"+9170{i:08d}"
        if not self.login(self.phone):
            raise StopUser()
        self.get("/api/auth/session")

    @task(6)
    def today(self):
        self.get("/api/auth/session")
        self.get("/api/pulse")
        self.get("/api/verdicts/today")
        self.get("/api/ask/coach")
        self.get("/api/plan")
        self.get("/api/inbox")
        self.get("/api/radar")

    @task(4)
    def verdicts(self):
        self.get("/api/verdicts/today")
        self.get("/api/picks/monday")
        sym = random.choice(COINS[:4])
        self.get(f"/api/verdicts/coin/{sym}", name="/api/verdicts/coin/[sym]")

    @task(2)
    def forecast(self):
        self.post("/api/verdicts/forecast", {"symbol": random.choice(COINS[:4]), "horizon_days": random.choice([7, 30])})

    @task(1)
    def debate(self):
        self.post("/api/verdicts/debate", {"symbol": random.choice(COINS[:4])})

    @task(3)
    def plan_paper(self):
        self.get("/api/plan")
        self.get("/api/paper")
        self.get("/api/portfolio")

    @task(1)
    def paper_trade(self):
        self.post("/api/paper/trade", {"symbol": random.choice(["BTC", "ETH", "SOL"]), "side": random.choice(["buy", "sell"]),
                                       "amount_inr": 1000})

    @task(3)
    def xray(self):
        self.post("/api/xray", {"query": random.choice(XRAY_QUERIES)})
        self.get("/api/xray/history")

    @task(2)
    def airdrops_autopilot(self):
        self.get("/api/airdrops")
        self.get("/api/autopilot")

    @task(2)
    def pro_pages(self):
        self.get("/api/news")
        self.get("/api/calendar?days=60", name="/api/calendar")
        self.get("/api/p2p?amount_inr=5000", name="/api/p2p")
        self.get("/api/baskets")

    @task(1)
    def ask(self):
        self.post("/api/ask", {"question": random.choice(["What is DCA?", "Is crypto legal in India?",
                                                          "How much should a beginner put in?"])})

    @task(1)
    def watch(self):
        self.post(f"/api/watchlist/{random.choice(COINS)}", name="/api/watchlist/[sym]")


class Admin(Base):
    """One staff member clicking through reports while members use the app."""
    wait_time = between(2, 5)
    fixed_count = 1

    def on_start(self):
        super().on_start()
        self.post("/api/qa/login", {"role": "admin"})

    @task(3)
    def pulse(self):
        self.get("/api/admin/pulse")

    @task(2)
    def webinar(self):
        # A webinar batch is 3 days (Day 1, Day 2, Day 3 call): the report the team actually pulls.
        end = datetime.now(IST).date()
        start = end - timedelta(days=2)
        self.get(f"/api/admin/webinar?start={start}&end={end}", name="/api/admin/webinar (3 days)")
        self.get(f"/api/admin/webinar/day3.csv?start={start}&end={end}", name="/api/admin/webinar/day3.csv (3 days)")

    @task(3)
    def users(self):
        self.get(f"/api/admin/users?q={random.choice(['Member 1', '+91700000', '9170000123', ''])}&page=1",
                 name="/api/admin/users?q=")
        self.get("/api/admin/users?plan=lite&page=3", name="/api/admin/users?plan=")

    @task(1)
    def jobs(self):
        self.get("/api/admin/jobs")


if SCENARIO == "spike":
    Member.abstract = True
    Admin.abstract = True
elif SCENARIO == "members":
    WebinarVisitor.abstract = True
    Admin.abstract = True
elif SCENARIO == "admin":
    WebinarVisitor.abstract = True
    Member.abstract = True
else:                                          # mixed: mostly members, some new visitors, one admin
    WebinarVisitor.weight = 1
    Member.weight = 4


@events.quitting.add_listener
def _summary(environment, **kw):
    s = environment.stats.total
    print(f"JOURNEYS completed={JOURNEYS['done']}")
    print(f"TOTAL requests={s.num_requests} failures={s.num_failures} rps={s.total_rps:.1f} "
          f"p50={s.get_response_time_percentile(0.5)} p95={s.get_response_time_percentile(0.95)} "
          f"p99={s.get_response_time_percentile(0.99)}")
