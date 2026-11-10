# Load test (3 Nov 2026)

## Setup

- Real MongoDB 8.3, seeded with **10,000 members** and 30 days of history:
  - 300,000 events
  - 6,000 plans
  - 1,500 paid subscriptions
  - 30,000 inbox alerts
  - 914 linked exchanges with Autopilot plans
- App on **2 web workers**, on a small test machine (2 CPUs, 7 GB). The load generator (Locust) ran on the same machine, so real servers will do better.
- Outside services were faked: AI, prices, exchanges, OTP SMS/WhatsApp.
- Every AI answer was made to take **3 seconds**, roughly like a real one.
- Scripts:
  - `scripts/seed_load.py`
  - `scripts/loadtest/locustfile.py`

## Results

**Test 1: webinar QR moment**

- **What happened:** 500 new people came in over about 1 minute. Each one used the free tools, signed up by OTP, made a plan, started Paper Money, ran Coin X-Ray, asked Ask Deepak and uploaded a chart.
- **Result:** 9,000 requests, 0 failed. All 500 signed up.
- **Speed:**
  - Normal pages: half under 0.03 s, 95% under 0.13 s.
  - AI answers: about 3 s.

**Test 2: 500 members at once for 5 minutes**

- **What happened:** members used every screen while 100 new people signed up and an admin opened the reports.
- **Result:** 59,485 requests, 0 failed. About 200 requests a second sustained.
- **Speed:**
  - Half under 0.007 s.
  - 95% under 0.03 s.
  - 99% under 0.14 s.

**Test 3: hard burst**

- **What happened:** 500 people arrived in 10 seconds, all from one shared IP, like a mobile carrier.
- **Result:** all 500 signed up.
- **Speed:** pages 0.5–1.5 s.
- **Problem:** 116 of 500 Chart Reader uploads got "busy, try again in a minute". Their usage was refunded.

## Fixed during testing

**Admin reports were slow on 10,000 members.** All tests ran on 10,000 members, but this was the only part of the app that slowed down.

| Report | Before | After |
|---|---|---|
| Webinar report | 15 s | 0.7 s |
| Day 3 CSV | 6 s | 0.9 s |
| Pulse | 3.9 s | about 0.2 s |

**Admin counts were wrong.**
- Members with an admin-given plan now count under that plan.
- Admin logins no longer count as webinar logins.
- Revoked accounts are no longer on the Day 3 list.

**More than one web worker was unsafe.** Scheduled jobs could run twice. A database lock now makes each job run once, so the app can use 2 or more workers (`WEB_CONCURRENCY`).

**OTP was blocked behind shared IPs.** The per-IP OTP limit was raised to 1,000 an hour. Indian mobile carriers put thousands of phones behind one IP, so the old limit of 30 would have blocked webinar sign-ups.

**AI calls had no queue.** They now queue with a limit per worker (`LLM_MAX_CONCURRENCY`, default 32) and a wait limit of 15 s. When the queue is full, the person sees "try again in a minute" and the use is refunded.

**News fetch could crash when two workers ran it together.** It no longer does.

## Follow-up fixes (4 Nov)

- **Chart Reader "busy" in the hard burst:** fixed with one AI pool per model class. Chart Reader (vision) has its own
  slots and a 45 s queue wait, `503` answers carry `Retry-After`, and the page retries twice by itself. Settings:
  `LLM_MAX_CONCURRENCY_<FAST|STRONG|VISION>` and `LLM_QUEUE_WAIT_S_<…>`. Watch live in Admin › Vendors › AI queues.
- **CoinGecko:** prices are now cached per coin (only missing coins are fetched), id lookups are cached, and each
  worker has a call budget (`COINGECKO_RATE_PER_MIN`). A 429 pauses calls and the last good value is served.
- **OTP:** pooled HTTP connections to MSG91 and AiSensy. A failing WhatsApp channel is skipped for 60 s so codes go straight to SMS.
- Re-run `scripts/loadtest/locustfile.py` (test 3) to confirm the Chart Reader number on your hardware.

## What the test can't tell you (check these live)

1. **AI capacity is the real limit.** Your Anthropic account's rate limits decide how many X-Rays, Ask Deepak answers and chart reads can run at once. In a webinar, keep the AI-heavy tools (Chart Reader, Ask Deepak) to a few people at a time, or raise the Anthropic limit beforehand.
2. **Price data limits.** CoinGecko's free plan allows about 30 calls a minute. The app caches prices, but use a paid CoinGecko key for webinars.
3. **OTP delivery.** MSG91 and AiSensy must be able to send 500 codes in a minute. Ask them about burst limits.
4. **Hosting.** Use at least 2 workers and a managed MongoDB (Atlas M10 or above) for the real launch.
