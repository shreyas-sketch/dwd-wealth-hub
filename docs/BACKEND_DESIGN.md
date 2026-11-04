# Backend design (build notes)

Source of reuse: `/home/claude/bullzeye/backend` (Bullzeye). Already copied into `backend/`:
`core/*` (settings, flags, health, observability, spa, vendors, deps, switches), `accounts/{otp_providers,otp_service,phone}.py`,
`growth/{clock,events}.py`, `crypto/exchanges/*`, `crypto/{vault,fx,tax,links,dca,copy}.py`, `billing/razorpay_client.py`,
`notify/channels.py`, `features/chart_vision.py` (from bullbear/vision.py). These still import Bullzeye-only modules
(e.g. `growth.plans`, `crypto.earn`) — adapt them; delete what is not needed (earn, grid, members, raydium, Finkhoz, stocks).

The contract the frontend builds against is `docs/API_CONTRACT.md` — match it exactly.

## Stack
FastAPI + Motor (Mongo). Python 3.12. Tests: pytest + mongomock-motor (no network), `cd backend && python -m pytest`.
One `server.py` (small): create app, CORS, include routers under `/api`, bind db, startup (indexes, flags refresh,
seed admin, seed demo content in QA), mount SPA last (`core.spa.mount_spa`). In-process APScheduler runs jobs when
`INPROCESS_SCHEDULER=true` (default true here — no Modal); `/api/jobs/tick` with `X-Ingest-Key` also runs due jobs for an
external cron. Brand from `BRAND_NAME` (default "Coinzeye").

## Vendors (core/vendors.py pattern: live | fake | off; QA_MODE=true → fake)
- `anthropic` (ANTHROPIC_API_KEY) — `llm.py`: `complete_json(task, system, prompt)`; models `LLM_MODEL_FAST` (claude-haiku-5-5),
  `LLM_MODEL_STRONG` (claude-sonnet-5-5), vision `LLM_MODEL_VISION` (claude-opus-5-5). Fake returns deterministic task-shaped JSON.
- `market` (no key needed: CoinGecko public, optional COINGECKO_API_KEY) — `market/provider.py`: `prices(symbols)`, `history(symbol, days)`
  (daily closes), `top_coins(n)`, `search(query)` (name/symbol/contract), `coin_detail(id)`, `global()` (total mcap, dominance),
  `trending()`; Fear & Greed from alternative.me; new listings from Binance `exchangeInfo` + KuCoin `/api/v2/symbols` snapshots.
  Fake: deterministic random walk seeded by symbol, realistic magnitudes (BTC ~68k, ETH ~3.4k, SOL ~160…), BTC monthly history back to 2016
  that includes a 2021 peak and 2022 drawdown so What If has a "worst start".
- `kronos` (KRONOS_API_URL/KEY) for forecasts; else statistical forecast (drift + volatility band). Reuse Bullzeye's request shape if simple.
- `goplus` (optional, no key) token security for contracts in X-Ray; fake.
- `news` RSS (CoinDesk, Cointelegraph, Decrypt); fake items.
- `p2p` Binance P2P search endpoint + KuCoin P2P (unofficial, best-effort, mark NEEDS verify); fake.
- `aisensy` WhatsApp (copied channels) for alerts; `email` optional; in-app inbox always.
- `razorpay` subscriptions (plan ids RAZORPAY_PLAN_LITE / RAZORPAY_PLAN_PRO); fake checkout in QA.
- `msg91`/aisensy for OTP (copied otp_providers); QA mode: OTP code returned as `dev_code` and also `000000` accepted.

## Plans & limits (`plans.py`)
free / lite (₹2,000) / pro (₹5,000). Effective plan = max(active paid sub, admin grant, trial) where trial = pro until
`users.trial_ends_at` (set at signup = now + settings.trial_days, default 3). Admin role → pro.
Limits per IST month (`usage` collection `{_id: uid:YYYY-MM, <feature>: n}`):
| feature | free | lite | pro |
|---|---|---|---|
| xray | 3 | 30 | ∞ |
| forecast | 0 | 10 | ∞ |
| debate | 0 | 10 | ∞ |
| chart | 0 | 10 | ∞ |
| ask | 0 | 0 | ∞ (fair use 300) |
Feature access: free → whatif, xray, verdicts (no details), plan (1, view), paper (view). lite adds verdict_details, pulse,
watchlist, monday_picks, paper_trade, airdrops, autopilot (BTC monthly), chart, forecast, debate. pro adds ask, baskets, radar,
calendar, p2p, news, autopilot all coins weekly/monthly, plans_max 3.
`require(db, user, feature)` → 403 locked; `consume(db, user, feature)` → 402 limit. Anonymous X-Ray: 1/day per anon cookie+IP.
Admin settings collection `settings` `{_id: "app", trial_days, scenario_rates, crash_levels, anon_xray_per_day}`.

## Features (one module each under `features/`)
- whatif: monthly DCA from monthly closes (INR via fx), invested/value/series; worst = start at the highest monthly close inside the window.
- xray: classify query (URL → link checks: lookalike exchange domains, punycode, odd TLD, http, known-scam words; free text →
  message checks: guaranteed/double returns, urgency, "send USDT/deposit", Telegram/WhatsApp groups, fake support; else coin lookup →
  rank, mcap, volume/mcap liquidity, age, change, goplus flags for contracts). Rules give score + flags; LLM writes headline and
  what_it_does (fake in QA). Top-10 coins attach today's verdict.
- verdicts: daily job (05:30 IST) for top 10 by mcap: indicators (RSI14, EMA20/50, 30d change, vol) → LLM committee (bull points, bear points,
  chair verdict + confidence) → `verdicts` (date, symbol). Change vs previous → inbox alert to watchers ("verdict changed").
  Forecast (Kronos or statistical) and Debate (LLM, deeper) on demand, metered. Pulse: prices, global, F&G, ETF flows (admin-entered
  `etf_flows`), cycle meter computed from halving dates (2016-07-09, 2020-05-11, 2024-04-20, next est 2028-04) and ATH drawdown.
  Watchlist. Monday Picks: admin publishes 2 coins + reasoning (`/admin/picks/suggest` = top 2 bullish by confidence).
- plan + paper: allocation by risk (safe: BTC 70/ETH 20/USDT 10; moderate: BTC 50/ETH 30/SOL 10/XRP 10; aggressive: BTC 40/ETH 25/SOL 20/XRP 15),
  scenarios from settings.scenario_rates (default bad 0%, average 15%, good 35% a year — labelled assumptions) compounding monthly with
  lump sum + monthly; yearly table. Goal progress from linked portfolio value else paper value. Paper ₹1,00,000, trades at live price,
  daily snapshot job for history. Portfolio from linked exchange balances (`links.adapter(...).balances()`).
- airdrops: admin CRUD; user step ticks (`airdrop_progress`). X-Ray result stored on save.
- autopilot: `crypto/links.py` + `crypto/dca.py` adapted (gate by plans, INR amounts, min ₹1,000, plan kinds coin|basket),
  daily 10:00 IST job; inbox note per buy and per failure ("top up USDT"). Daily key re-verify 05:30.
- chart: adapt `chart_vision.py` to crypto/any price chart; fake returns a sample read.
- ask: KB = admin-uploaded .txt/.vtt/.md (strip VTT timecodes) → chunks (~350 words) in `kb_chunks`; retrieval = simple BM25 in Python
  over chunk tokens; LLM answers in Deepak's teaching voice from the chunks only, refuses personal buy/sell calls ("should I buy X")
  with a pointer to Coin X-Ray/Verdicts; threads stored. Coach: goal from the user's first plan; crash job (hourly) — BTC drawdown from
  30-day high ≥ a crash level → one alert per level per 7 days to pro users with the admin's crash note; `/ask/coach` shows it.
- baskets: admin CRUD; practice → paper buys by weight; invest → check USDT balance ≥ total, then market buy per coin
  (`market_buy_quote`), min ₹1,000 per coin, coins must be listed on both venues (validate on admin save against a known list);
  autopilot → DcaPlan kind basket. Basket change (weights/coins) → inbox alert to holders ("X removed — tap to sell" style text).
- radar: hourly job: new listings diff (Binance + KuCoin symbol snapshots) + trending → auto X-Ray → `radar_items`; daily inbox digest to pro.
- calendar: `crypto_events` admin CRUD + seeded halving; `yours` when a coin is in watchlist/plan/holdings; day-before inbox alert job.
- p2p: cached 5 min; safety high = completion ≥ 98% and orders ≥ 500, medium ≥ 95%/100, else low; tips list.
- news: job every 2 h: fetch RSS, tag coins by name/symbol, LLM summary + what_it_means + sentiment (batch); `yours` by user coins;
  `/news/check` LLM verdict real/hype/unclear.

## Admin
Routes per contract. Admin = `users.role == "admin"`: phones in `ADMIN_PHONES` get admin on OTP login; staff login by
`ADMIN_EMAIL` / `ADMIN_PASSWORD` (bcrypt, seeded on startup). Jobs registry with last-run rows (`job_runs`).
Webinar report + Day 3 CSV = accounts created in [start, end] whose effective paid plan is none.

## QA
`QA_MODE=true` → all vendors fake, `/api/qa/login` enabled, demo content seeded (airdrops, baskets, events, picks, crash notes, KB sample,
ETF flows, verdicts for today, radar, news) so every screen has data. `scripts/qa_server.py` starts uvicorn with mongomock or a local Mongo
(prefer mongomock-motor in-process so no Mongo is needed) on :8765 serving the built frontend.
