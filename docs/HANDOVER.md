# Coinzeye — developer handover (3 Nov 2026)

A new, separate app for the DWD crypto funnel. It is built on Bullzeye's code, with Bullzeye's look and a new colour mix (cool grey panels, Bitcoin-orange highlights).

- **Status:** runs end to end on sample data.
- **Tests:** 54 backend tests pass.
- **Frontend:** builds clean.
- **Not done yet:** nothing has been run against the live data sources (this workspace had no internet access to them).

## 1. What's in it

**Free open page (`/`), no login needed**
- What If calculator
- 1 Coin X-Ray a day
- Market Pulse, including the Bitcoin Cycle Meter
- "Create free account" button

**Login**
- WhatsApp or SMS OTP.
- A new number creates the account straight away. This is how webinar attendees sign up.
- New accounts get the ₹5,000 plan as a trial for 3 days. Change the length in Admin › Settings.

**₹2,000 plan**
- Coin X-Ray (Scam Check is inside it)
- Crypto Verdicts, including Pulse, Cycle Meter, watchlist alerts and Monday Picks
- My Crypto Plan, with Paper Money inside it
- Airdrop Finder
- SIP Autopilot
- Chart Reader

**₹5,000 plan:** everything in ₹2,000 without limits, plus:
- Ask Deepak AI (with Goal Tracker and Crash Coach)
- Crypto Baskets
- Early Coin Radar
- Events Calendar
- P2P Rate Finder
- News Decoder

**Admin (`/admin`)**
- Pulse KPIs
- Webinar report, with a Day 3 CSV of people who signed up but didn't pay
- Users: grant a plan, extend a trial, revoke
- Content editors: airdrops, baskets, events, Monday Picks, crash notes, knowledge base, ETF flows
- Features (on/off switches), Settings, Vendors, and Jobs with "Run now"

## 2. Reused from Bullzeye

**Almost unchanged**
- Core plumbing: settings, feature flags, vendor switches, health, SPA serving
- OTP service and phone helpers
- Event log
- Encrypted exchange-key vault
- Tax ledger
- KuCoin and Binance adapters

**Adapted**
- Exchange linking. Keys that can withdraw are still refused, and every key is re-checked daily.
- Autopilot buys: rupee amounts, coin or basket plans, and a USDT check before buying.
- Razorpay client
- WhatsApp channel
- Chart Reader (from Bull/Bear "I have a chart")

**New**
- Server, plans and limits, billing routes, inbox, jobs, market data, AI helper, admin API
- All 13 features
- The whole frontend shell and its pages (the visual style is Bullzeye's)

## 3. Run it

See the README. The short version:

```bash
cd backend && pip install -r requirements-dev.txt
cd ../frontend && yarn install && yarn build
cd ../backend && python ../scripts/qa_server.py     # http://localhost:8765, sample data
```

## 4. Before launch (NEEDS)

1. **Keys.** Fill in `backend/.env.example`. You need:
   - `MONGO_URL` and `JWT_SECRET`
   - `ANTHROPIC_API_KEY`
   - `EXCHANGE_VAULT_KEY`
   - Razorpay keys plus the two plan ids (`RAZORPAY_PLAN_LITE`, `RAZORPAY_PLAN_PRO`)
   - MSG91 / AiSensy for OTP
   - `ADMIN_PHONES`, `ADMIN_EMAIL` and `ADMIN_PASSWORD`
   - `BRAND_NAME`
2. **Check each live data source once with internet access.** Parsing is tested only against mocked responses:
   - CoinGecko (prices, history, search, trending, global)
   - alternative.me (Fear & Greed)
   - Binance and KuCoin symbol lists
   - GoPlus (contract checks)
   - RSS news feeds
3. **P2P rates.** The Binance and KuCoin P2P endpoints are the ones their own web pages use, not documented APIs. Test them from the server. If they block servers, set `P2P_MODE=off`.
4. **ETF flows.** There's no data feed. The team types them in under Admin › ETF flows.
5. **Token unlocks.** No vendor is wired in. Unlocks go in by hand under Admin › Events until a vendor is chosen.
6. **Exchange keys.**
   - Confirm whether KuCoin or Binance trade keys need a fixed server IP. If they do, give Railway a static outbound IP and tell users to whitelist it.
   - Move the vault master key to a KMS before public launch.
7. **Workers.** Run 2 or more web workers (`WEB_CONCURRENCY`, default 2). A database lock makes each scheduled job run once. Load test results are in `docs/LOAD_TEST.md`.
8. **Razorpay pricing.** Prices are ₹2,000 + GST and ₹5,000 + GST. Create the Razorpay plans at ₹2,360 and ₹5,900 a month.
9. **Counsel.** Get a view on the coin-level calls in Verdicts, Monday Picks, Baskets and the Radar, and on placing orders on users' own exchange accounts.

## 5. Content the team loads in Admin

- **Knowledge base for Ask Deepak AI.** Upload Deepak's session transcripts as .txt, .vtt or .md. The QA sample is placeholder text.
- **Monthly content:**
  - Crash notes for the 20%, 30% and 40% falls
  - The live baskets
  - Weekly airdrops
  - Monday Picks
  - Events
- **Settings:** trial days, scenario rates for the plan, crash levels.

## 6. Webinar run sheet

1. Put a QR code on screen pointing to `https://<domain>/?utm_source=webinar&utm_campaign=<batch>`.
2. Attendees log in by WhatsApp OTP in the first 20 minutes.
3. Day 1 tools: What If, then Coin X-Ray.
4. Day 2 tools: My Crypto Plan + Paper Money, then Verdicts, then Ask Deepak AI.
5. On Day 3, open Admin › Webinar for the batch dates and download the Day 3 CSV. That's the list for the ₹2,000 call.

## 7. Docs

- `docs/API_CONTRACT.md`: every endpoint
- `docs/BACKEND_DESIGN.md`: how each feature works
- `frontend/README.md`: routes, and where the name and colours live
