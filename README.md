# Coinzeye

Crypto learning + research app for DWD members, sold as a monthly subscription
(₹2,000 + GST and ₹5,000 + GST plans) after the ₹99 webinar. Free open page for webinar attendees,
WhatsApp-OTP sign-up, member app, and an admin panel. Built on Bullzeye's code where it fits.

**Name:** "Coinzeye" is a placeholder. Change it in `frontend/src/brand.js` (web) and `BRAND_NAME` (server).

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI app (`server.py`), one module per feature in `features/`, admin API in `admin/` |
| `backend/market/` | Crypto prices/history/search (live public APIs or a deterministic fake) |
| `backend/crypto/` | Exchange rails from Bullzeye: KuCoin/Binance adapters, key vault, Autopilot buys |
| `backend/jobs/` | Scheduled jobs (verdicts 05:30, Autopilot 10:00, radar hourly, news 2-hourly …) |
| `frontend/` | React app (Bullzeye look), built into the image and served by FastAPI |
| `scripts/qa_server.py` | Whole app on sample data — no Mongo, no keys, no network |
| `docs/` | API contract and backend design notes |

## Run locally (QA mode, sample data)

```bash
cd backend && pip install -r requirements-dev.txt
cd ../frontend && yarn install && yarn build      # optional: without it only the API runs
cd ../backend && python ../scripts/qa_server.py   # http://localhost:8765
```

QA mode: every vendor is fake, demo content is seeded, the OTP code is shown on screen (000000 also works),
and `POST /api/qa/login` logs in demo users (`{}` = ₹5,000 trial, `{"plan":"lite"}`, `{"plan":"free"}`,
`{"role":"admin"}` → open `/admin`).

## Tests

```bash
cd backend && python -m pytest -q          # no network, mongomock
```

## Run against a real database

```bash
cp backend/.env.example backend/.env       # fill MONGO_URL, JWT_SECRET, … (COOKIE_SECURE=false for http)
cd backend && uvicorn server:app --reload --port 8001
```

## Deploy (Railway)

The root `Dockerfile` builds the frontend and serves it from FastAPI (`railway.json`, health check
`/api/health`). Set the variables from `backend/.env.example`. Run 2+ workers (`WEB_CONCURRENCY`); a Mongo lock makes
each scheduled job run once. Load test: `docs/LOAD_TEST.md`.

## Plans

| | Free | ₹2,000 | ₹5,000 |
|---|---|---|---|
| Coin X-Ray (+ Scam Check) | 3/month | 30/month | unlimited |
| Crypto Verdicts (+ Pulse, Cycle Meter, watchlist, Monday Picks) | verdicts only | full; 10 Forecasts + 10 Debates | unlimited |
| My Crypto Plan + Paper Money | view | 1 plan, trades | 3 plans |
| Airdrop Finder · Chart Reader | — | ✓ · 10/month | ✓ · unlimited |
| SIP Autopilot | — | BTC monthly | BTC/ETH/SOL/XRP weekly/monthly |
| Ask Deepak AI · Baskets · Coin Radar · Events Calendar · P2P Rates · News Decoder | — | — | ✓ |

New accounts get the ₹5,000 plan as a trial for `trial_days` (Admin › Settings, default 3).
