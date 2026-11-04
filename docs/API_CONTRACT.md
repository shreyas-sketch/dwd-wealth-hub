# API contract (v1, 3 Nov 2026)

Working name: **Coinzeye** (placeholder — the brand lives in `frontend/src/brand.js` and `BRAND_NAME`).
Everything is under `/api`. Auth = httpOnly cookies (`access_token`, `refresh_token`) set by OTP verify;
the frontend uses axios with `withCredentials: true`.

## Conventions

- Errors: HTTP 4xx with `{"detail": {"code": "...", "msg": "human sentence", ...}}`.
- `401` → not logged in. Frontend sends the user to `/login?next=<path>`.
- `402` limit reached → `{"detail": {"code": "limit", "msg", "feature", "used", "limit", "plan_needed": "lite"|"pro"}}`.
- `403` plan locked → `{"detail": {"code": "locked", "msg", "feature", "plan_needed": "lite"|"pro"}}`.
- Money: `_inr` fields are rupees (number), `_usd` are dollars. Dates ISO strings (UTC). `pct` fields are percentages (12.5 = 12.5%).
- Every response that shows research carries `disclaimer` (string) where noted.
- `usage` = `{"used": n, "limit": n|null}` (null = unlimited) after a metered call.

Plans: `free`, `lite` (₹2,000/month), `pro` (₹5,000/month). New accounts get a **trial** of `pro`
for `trial_days` (admin setting, default 3) so webinar attendees can use everything until the Day 3 call.

Feature keys (used in `features`, `locked` errors, and the frontend):
`whatif, xray, verdicts, verdict_details, forecast, debate, pulse, watchlist, monday_picks, plan, paper_trade,
airdrops, autopilot, chart, ask, baskets, radar, calendar, p2p, news`

## Auth

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /auth/otp/request | `{phone, channel?: "auto"\|"sms"\|"whatsapp"}` | `{challenge_id, channel, sent_to, expires_in, resend_in, is_new, dev_code?}` (`dev_code` only in QA mode) |
| POST | /auth/otp/verify | `{challenge_id, phone, code, name?, utm?, device_id?}` | `{user, is_new}` + cookies. **Creates the account if the number is new.** |
| GET | /auth/me | — | `{user, plan: PlanInfo}` (401 if logged out) |
| POST | /auth/logout | — | `{ok}` |
| POST | /auth/refresh | — | `{ok}` |
| PATCH | /auth/profile | `{name?, email?}` | `{user}` |
| POST | /auth/staff/login | `{email, password}` | `{user}` (admin staff login) |
| POST | /qa/login | `{phone?, role?: "user"\|"admin", plan?: "free"\|"lite"\|"pro"}` | QA mode only: logs in a demo user |

`user` = `{id, phone, name, email, role: "user"|"admin", created_at}`

`PlanInfo` (also `GET /me/plan`):
```json
{"plan": "pro", "label": "₹5,000 plan", "source": "trial|paid|grant|free",
 "trial_ends_at": "…|null", "paid_until": "…|null", "cancelling": false,
 "features": {"xray": true, "ask": true, ...},
 "limits": {"xray": {"used": 2, "limit": 30}, "forecast": {...}, "debate": {...}, "chart": {...}, "ask": {...}},
 "autopilot": {"coins": ["BTC"], "frequencies": ["monthly"]},
 "plans_max": 1}
```

`GET /plans/catalog` (public) → `{"trial_days": 3, "plans": [{"id": "free|lite|pro", "name", "price_inr", "period": "month", "features": ["line", ...]}]}`

## Public (no login)

| Method | Path | Notes |
|---|---|---|
| GET | /public/pulse | MarketPulse (below) |
| POST | /whatif | `{monthly_inr, coin: "BTC"\|"ETH"\|"SOL", years: 3\|5}` → WhatIf |
| POST | /xray | `{query}` → XRay. Anonymous: 1 check a day; logged in: plan limit |
| GET | /verdicts/today | Free/anon get verdict + confidence only; lite+ also `bull`, `bear`, `chair` |

WhatIf:
```json
{"coin": "BTC", "monthly_inr": 5000, "years": 5, "invested_inr": 300000, "value_inr": 812000, "return_pct": 170.6,
 "series": [{"month": "2021-11", "invested_inr": 5000, "value_inr": 5000}],
 "worst": {"start": "2021-11", "invested_inr": 300000, "value_inr": 410000, "return_pct": 36.6, "note": "Started at the 2021 peak"},
 "note": "Past prices, not a promise of future returns."}
```

XRay:
```json
{"kind": "coin|link|message", "query": "…", "label": "safe|risky|likely_scam", "score": 72,
 "headline": "One-line plain answer",
 "red_flags": [{"title": "…", "detail": "…", "severity": "high|medium|low"}],
 "green_flags": ["…"],
 "coin": {"symbol", "name", "rank", "price_usd", "market_cap_usd", "volume_24h_usd", "change_24h", "age_days", "chain", "contract"} ,
 "what_it_does": "…",
 "verdict": Verdict|null,
 "usage": {"used": 1, "limit": 3}, "disclaimer": "…"}
```
`score` = risk 0–100 (higher = riskier). `coin`, `what_it_does`, `verdict` only for `kind: coin`.
`GET /xray/history` → `{items: [{query, kind, label, score, at}]}`

## Crypto Verdicts

Verdict:
```json
{"symbol": "BTC", "name": "Bitcoin", "price_usd": 68000, "change_24h": 1.2,
 "verdict": "Bullish|Neutral|Bearish", "confidence": 68, "changed_from": "Neutral|null",
 "summary": "One line", "bull": ["…"], "bear": ["…"], "chair": "…", "watched": false, "date": "2026-11-03"}
```
| Method | Path | Returns |
|---|---|---|
| GET | /verdicts/today | `{date, updated_at, coins: [Verdict], disclaimer}` |
| GET | /verdicts/coin/{symbol} | `{coin, verdict, history: [{date, verdict, confidence}], disclaimer}` |
| POST | /verdicts/forecast | `{symbol, horizon_days: 7\|30}` → Forecast |
| POST | /verdicts/debate | `{symbol}` → Debate |
| GET | /pulse | MarketPulse (lite+; the public version is `/public/pulse`) |
| GET | /watchlist | `{symbols: [..]}` |
| POST / DELETE | /watchlist/{symbol} | `{symbols}` |
| GET | /picks/monday | `{week_of, published, picks: [{symbol, name, verdict, confidence, reasoning, price_at_pick_usd, price_now_usd, change_pct}], disclaimer}` |

Forecast: `{symbol, horizon_days, last_price_usd, expected_price_usd, low_usd, high_usd, expected_move_pct,
path: [{day, price_usd, low_usd, high_usd}], model: "kronos|statistical", as_of, usage, disclaimer}`

Debate: `{symbol, bull: [{point, evidence}], bear: [{point, evidence}], chair: {verdict, confidence, call}, as_of, usage, disclaimer}`

MarketPulse:
```json
{"coins": [{"symbol": "BTC", "price_usd", "price_inr", "change_24h"}],
 "total_mcap_usd", "btc_dominance_pct",
 "fear_greed": {"value": 54, "label": "Neutral"},
 "etf_flows": {"date", "net_usd_m", "note"} ,
 "cycle": {"last_halving": "2024-04-20", "next_halving_est": "2028-04", "days_since", "days_to_next",
           "phase": "Expansion", "phase_note": "…", "ath_usd", "drawdown_from_ath_pct", "position_pct"},
 "as_of"}
```
`position_pct` = 0–100 position through the 4-year cycle (for the meter).

## My Crypto Plan + Paper Money

CryptoPlan:
```json
{"id", "goal_name", "target_inr", "lump_sum_inr", "monthly_inr", "years", "risk": "safe|moderate|aggressive",
 "allocation": [{"symbol": "BTC", "pct": 50}],
 "invested_total_inr",
 "scenarios": [{"key": "bad|average|good", "label", "annual_pct", "end_value_inr", "reaches_goal"}],
 "yearly": [{"year": 1, "invested_inr", "bad_inr", "average_inr", "good_inr"}],
 "goal_progress": {"value_inr", "pct", "source": "portfolio|paper|none"},
 "paper_started": true, "created_at", "note"}
```
| Method | Path | Body / Returns |
|---|---|---|
| GET | /plan | `{plans: [CryptoPlan], max}` |
| POST | /plan | `{goal_name, target_inr, lump_sum_inr, monthly_inr, years, risk}` → CryptoPlan |
| PUT / DELETE | /plan/{id} | same body / `{ok}` |
| GET | /portfolio | `{linked: ["kucoin"], holdings: [{venue, symbol, qty, price_usd, value_usd, value_inr}], total_inr, total_usd, vs_plan: [{symbol, plan_pct, actual_pct}], as_of}` |
| GET | /paper | Paper |
| POST | /paper/start | `{plan_id}` → Paper (₹1,00,000 split by the plan's allocation) |
| POST | /paper/trade | `{symbol, side: "buy"\|"sell", amount_inr}` → Paper (needs lite+) |
| POST | /paper/reset | → Paper |

Paper: `{start_inr, cash_inr, value_inr, pnl_inr, pnl_pct, positions: [{symbol, qty, avg_price_inr, price_inr, value_inr, pnl_pct}], history: [{date, value_inr}], plan_id, can_trade, started_at}`

## Airdrop Finder (lite+)

`GET /airdrops` → `{items: [{id, name, coin, chain, status: "live|ended", reward, deadline, link, description,
steps: [{id, text}], done_steps: [id], xray: {label, score}}]}`
`POST /airdrops/{id}/steps/{step_id}` `{done: bool}` → the item.

## SIP Autopilot (lite: BTC monthly; pro: BTC/ETH/SOL/XRP weekly or monthly)

| Method | Path | Body / Returns |
|---|---|---|
| GET | /autopilot | `{enabled, venues: [{venue, linked, key_tail, status, reason}], plans: [DcaPlan], allowed: {coins, frequencies}, min_inr: 1000}` |
| POST | /autopilot/link | `{venue: "kucoin"\|"binance", api_key, api_secret, passphrase?}` → venue row |
| DELETE | /autopilot/link/{venue} | `{ok}` |
| GET | /autopilot/balance/{venue} | `{usdt, inr_est}` |
| POST | /autopilot/plan | `{venue, coin, amount_inr, frequency: "weekly"\|"monthly", weekday?: 0-6, day?: 1-28}` → DcaPlan |
| POST | /autopilot/plan/{id}/pause, /resume | DcaPlan |
| DELETE | /autopilot/plan/{id} | `{ok}` |

DcaPlan: `{id, kind: "coin|basket", venue, coin, basket_id, amount_inr, frequency, weekday, day, status: "active|paused",
next_at, last_error, buys, invested_inr, value_inr, return_pct, recent: [{at, coin, qty, price_usd, inr}]}`

## Chart Reader (lite: 10/month)

`POST /chart` multipart `file` (+ optional `symbol`) →
`{is_chart, symbol, timeframe, trend: "up|down|sideways", summary, support: [str], resistance: [str], rsi_read,
patterns: [str], what_to_watch: [str], usage, disclaimer}`. Not a chart → `400 {"code": "not_chart"}`.

## Ask Deepak AI (pro)

| Method | Path | Body / Returns |
|---|---|---|
| POST | /ask | `{question, thread_id?}` → `{thread_id, answer, sources: [{title, snippet}], refused, usage}` |
| GET | /ask/threads | `{items: [{id, title, updated_at}]}` |
| GET | /ask/threads/{id} | `{id, messages: [{role: "user"\|"assistant", text, sources?, at}]}` |
| GET | /ask/coach | `{goal: {name, target_inr, value_inr, pct, source}|null, crash: {active, level, drawdown_pct, note, at}|null}` |

## Crypto Baskets (pro)

Basket: `{id, name, theme, description, coins: [{symbol, weight_pct}], min_inr, risk_note, change_note, changed_at}`
| Method | Path | Body / Returns |
|---|---|---|
| GET | /baskets | `{items: [Basket]}` |
| POST | /baskets/{id}/practice | `{amount_inr}` → Paper |
| POST | /baskets/{id}/invest | `{venue, amount_inr}` → `{orders: [{symbol, inr, qty, price_usd, status}], total_inr}` (409 `{code: "short_usdt"}` if balance too low) |
| POST | /baskets/{id}/autopilot | `{venue, amount_inr, frequency, weekday?, day?}` → DcaPlan |

## Early Coin Radar (pro)

`GET /radar` → `{as_of, items: [{id, symbol, name, kind: "new_listing|trending", venue, listed_at, price_usd, change_24h,
xray: {label, score, red_flags: [str]}, seen_at}]}`

## Crypto Events Calendar (pro)

`GET /calendar?days=60` → `{items: [{id, date, title, kind: "unlock|listing|upgrade|halving|macro|etf", coins: [str],
impact: "high|medium|low", note, yours}]}`

## P2P Rate Finder (pro)

`GET /p2p?amount_inr=5000` → `{asset: "USDT", fiat: "INR", as_of, venues: [{venue, best_price,
offers: [{merchant, price, min_inr, max_inr, completion_pct, orders, payment: [str], safety: "high|medium|low"}]}], tips: [str]}`

## News Decoder (pro)

`GET /news` → `{items: [{id, title, source, url, published_at, coins, summary, what_it_means, sentiment: "positive|negative|neutral", yours}]}`
`POST /news/check` `{text}` (a link or pasted text) → `{verdict: "real|hype|unclear", reasons: [str], summary}`

## Inbox (alerts)

`GET /inbox` → `{unread, items: [{id, kind, title, body, link, at, read}]}` · `POST /inbox/read-all` → `{ok}`

## Billing

| Method | Path | Body / Returns |
|---|---|---|
| POST | /billing/checkout | `{plan: "lite"\|"pro"}` → `{mode: "razorpay"\|"fake", subscription_id, key_id, amount_inr, plan, name, prefill: {contact}}` |
| POST | /billing/verify | `{subscription_id, payment_id, signature}` → `{plan: PlanInfo}` (fake mode: any values) |
| POST | /billing/cancel | `{status: "cancels_at_period_end", access_until}` (PlanInfo.cancelling turns true) |
| POST | /billing/razorpay/webhook | Razorpay |

## Analytics

`POST /events` `{name, props}` — client event names: `page_view, tool_opened, upgrade_viewed, checkout_opened, share_clicked`.

## Admin (role admin) — prefix `/admin`

| Method | Path | Notes |
|---|---|---|
| GET | /admin/pulse | `{kpis: {users_total, signups_today, signups_7d, trial_active, lite_active, pro_active, mrr_inr, paid_conversion_pct}, signups_by_day: [{date, count}], by_source: [{source, count}], feature_usage_7d: [{feature, count}], plan_mix: [{plan, count}]}` |
| GET | /admin/webinar?start=YYYY-MM-DD&end=YYYY-MM-DD | `{signups, logins, feature_usage: [{feature, users, uses}], bought: {lite, pro}, day3_list_count}` |
| GET | /admin/webinar/day3.csv?start&end | CSV of accounts created in the window who have not paid |
| GET | /admin/users?q=&plan=&page= | `{total, items: [{id, phone, name, plan, source, created_at, last_login_at, trial_ends_at, paid_until, status}]}` |
| GET | /admin/users/{id} | `{user, plan, usage, events: [{name, ts, props}]}` |
| POST | /admin/users/{id}/grant | `{plan: "lite"\|"pro"\|"free", months}` |
| POST | /admin/users/{id}/trial | `{days}` |
| POST | /admin/users/{id}/status | `{status: "active"\|"revoked"}` |
| GET / POST | /admin/flags | list / `{key, on: true\|false\|null}` |
| GET / POST | /admin/settings | `{trial_days, scenario_rates: {bad, average, good}, crash_levels: [20, 30, 40], anon_xray_per_day}` |
| GET | /admin/vendors | `{vendors: [{name, mode}]}` |
| GET / POST / PUT / DELETE | /admin/airdrops[/{id}] | Airdrop fields (no done_steps) |
| GET / POST / PUT / DELETE | /admin/baskets[/{id}] | Basket fields |
| GET / POST / PUT / DELETE | /admin/events[/{id}] | Event fields |
| GET / POST | /admin/picks | `{week_of, published, picks: [{symbol, reasoning}]}`; `GET /admin/picks/suggest` → 2 suggested coins |
| GET / POST | /admin/crash-notes | `{notes: [{level: 20, note}]}` |
| GET / POST / DELETE | /admin/kb[/{id}] | list docs `{items: [{id, title, chunks, words, uploaded_at}]}`; POST multipart `file` + `title` |
| GET / POST | /admin/etf-flows | `{items: [{date, net_usd_m, note}]}` / `{date, net_usd_m, note}` |
| GET | /admin/jobs | `{items: [{name, schedule, last: {at, ok, result}}]}` |
| POST | /admin/jobs/{name}/run | `{ok, result}` |
