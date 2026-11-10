# QA report (2–3 Nov 2026)

How it was tested:
- Every endpoint was called through the API for each persona: anonymous, free, ₹2,000, ₹5,000 trial, paid, admin.
- Every screen was clicked through with Playwright at 390px and 1280px, in light and dark mode.
- The QA server ran on port 8766.

Result:
- Backend tests: 78 pass (`python -m pytest -q`). 20 of them are new, in `backend/tests/test_qa_regressions.py`.
- Frontend: `CI=false yarn build` compiles.
- Final crawl: no 5xx, no page errors, no sideways scroll at 390px, no "NaN" or "undefined" on any screen.


## Bugs fixed

Each bug is listed as: what was wrong, what changed, how it was checked.

**1. Coin X-Ray called look-alike sites safe**
- Wrong: `blnance.com`, `kuc0in.com`, `wazrix.com` and any unknown site came back "Looks safe — This looks like an official site".
- Changed: look-alike spelling check (one or two letters off, digits for letters, swapped letters). Unknown sites get a low flag and a cautious headline. Added opensea.io, pancakeswap.finance and trustwallet.com to the official list. File: `features/xray.py`.
- Checked: API, UI, and a test.

**2. X-Ray brand names spelled wrong**
- Wrong: "The real Kucoin site…" (also Metamask, Okx).
- Changed: proper brand names. File: `features/xray.py`.
- Checked: a test.

**3. Blank X-Ray used up a check**
- Wrong: a query of only spaces used a check and answered "Not found".
- Changed: it now returns 400 "Type a coin name…". File: `features/xray.py`.
- Checked: a test.

**4. X-Ray missed common coin spellings**
- Wrong: "$PEPE" and "pepe coin" were "not found".
- Changed: strip the leading $ or # and a trailing "coin" or "token". File: `features/xray.py`.
- Checked: a test.

**5. "Kucoin" in user messages**
- Wrong: link, balance, top-up and buy alerts and the radar digest said "Kucoin".
- Changed: they now say "KuCoin". Files: `crypto/__init__.py` (venue_name), `crypto/links.py`, `crypto/dca.py`, `features/autopilot.py`, `features/radar.py`.
- Checked: a test.

**6. Admin › Settings crashed on bad input**
- Wrong: a value like "abc" gave a 500.
- Changed: it now returns 400 `bad_setting` with a plain message. File: `appsettings.py`.
- Checked: a test.

**7. ₹5,000 member at the 3-plan limit was told to upgrade**
- Wrong: the message read "The ₹5,000 plan holds 3" and the upgrade sheet opened.
- Changed: 400 `plans_full` "Delete one to make a new one". File: `features/plan.py`.
- Checked: a test.

**8. ₹2,000 member picking ETH or weekly Autopilot got the wrong message**
- Wrong: it said "SIP Autopilot is part of the ₹5,000 plan".
- Changed: it now says "On ₹2,000 Autopilot buys Bitcoin once a month…". File: `features/autopilot.py`.
- Checked: a test.

**9. Fake exchange accepted a key with "withdraw" in the middle**
- Wrong: only keys starting with "withdraw" were refused.
- Changed: any key containing "withdraw" is refused. File: `crypto/exchanges/fake.py`.
- Checked: a test.

**10. Airdrop with a scam link showed "Looks safe"**
- Wrong: only the coin was X-Rayed, not the link.
- Changed: both are checked and the riskier answer is shown. File: `features/airdrops.py`.
- Checked: API, admin UI, and a test.

**11. Bad dates were saved**
- Wrong: an airdrop deadline of "tomorrow" and an event date of 2026-02-30 were accepted.
- Changed: both are now validated. Files: `features/airdrops.py`, `features/calendar.py`.
- Checked: a test.

**12. Upgrading ₹2,000 → ₹5,000 left both subscriptions renewing**
- Wrong: the member would be charged twice every month.
- Changed: the older subscription is set to cancel at the end of its paid month. File: `billing/routes.py`.
- Checked: a test.

**13. Cancel subscription showed a raw code**
- Wrong: it showed "Subscription: cancels_at_period_end", the Cancel button stayed, and the plan never showed as cancelled.
- Changed: PlanInfo now has `cancelling`. Account shows "cancelled, ends <date>" and hides the button. Files: `plans.py`, `billing/routes.py`, `pages/Account.jsx`, `API_CONTRACT.md`.
- Checked: UI and a test.

**14. Limit message said "10 Bull vs Bear debate checks"**
- Changed: each feature now has its own word ("10 Bull vs Bear debates", "10 Forecasts"). File: `plans.py`.
- Checked: a test.

**15. What If "worst start" sentence repeated itself**
- Changed: the note is shorter. File: `features/whatif.py`.
- Checked: a test and a screenshot.

**16. Crash alert body was empty for a level without a note** (for example 5%)
- Changed: a default note is used. File: `features/ask.py`.
- Checked: a test.

**17. Locked pages showed the lock card twice**
- Wrong: on the free and ₹2,000 plans, Airdrops, Baskets, Radar, Calendar, P2P and News still called the API. The 403 opened a second lock sheet over the page.
- Changed: queries now wait for the feature flag. Files: `pages/Airdrops.jsx`, `Radar.jsx`, `Baskets.jsx`, `Calendar.jsx`, `P2P.jsx`, `News.jsx`, `Autopilot.jsx`.
- Checked: crawl (no 403s) and screenshot.

**18. Raw server wording shown to members**
- Wrong: for example "Input should be less than or equal to 1000000".
- Changed: 422 answers are turned into plain sentences, like "Target amount must be at least ₹10,000." File: `lib/api.js`.
- Checked: UI.

**19. What If kept an old answer on odd inputs**
- Wrong: -500 or 2500.75 was silently blocked by the browser, the old result stayed, and 999999999 showed raw text.
- Changed: the form does its own checks with plain messages (₹100 to ₹10,00,000). Files: `WhatIf.jsx`, `ui.jsx` MoneyInput.
- Checked: UI.

**20. Money boxes were silently blocked**
- Wrong: Autopilot ₹999 and decimal amounts did nothing, with no message, because of the browser's own min/step check.
- Changed: MoneyInput accepts paise and ignores the native min. The API or screen gives the message. File: `components/ui.jsx`.
- Checked: UI.

**21. Profile Save did nothing for a bad email**
- Wrong: the browser blocked the form, so our message never showed.
- Changed: the form is `noValidate` and our message shows. File: `pages/Account.jsx`.
- Checked: UI.

**22. P2P with ₹50 said "Could not load P2P rates… Try again"**
- Changed: it now shows an inline "Enter an amount between ₹100 and…". File: `pages/P2P.jsx`.
- Checked: UI.

**23. Selling more than you hold said "Sold ₹99,99,999 of XRP"**
- Changed: it now shows the real amount, plus "all you held". File: `plan/PaperSection.jsx`.
- Checked: UI.

**24. Tables were cut off at 390px**
- Wrong: the "Good" column of the year-by-year table and Value/P&L in Paper positions were hidden off-screen.
- Changed: short rupees (₹19.7 L) on phones, and Qty is hidden on phones. Files: `plan/PlanCard.jsx`, `plan/PaperSection.jsx`.
- Checked: screenshot.

**25. Dates and greeting followed the phone's time zone, not IST**
- Wrong: at 02:00 IST it showed "2 Nov · Good evening".
- Changed: IST everywhere. Date-only values never shift. Admin Monday-of-week and ETF default date use IST. Files: `lib/format.js`, `pages/Today.jsx`, `pages/Calendar.jsx`, `admin/shared.jsx`, `admin/Picks.jsx`, `admin/EtfFlows.jsx`.
- Checked: UI.

**26. Raw ISO and lowercase text on screens**
- Wrong: the ETF flow date showed as "2026-11-02", and Today's radar showed "binance · kucoin".
- Changed: both are formatted. Files: `components/Pulse.jsx`, `pages/Today.jsx`.
- Checked: screenshot.

**27. A revoked member stayed on a broken page**
- Changed: a 403 `revoked` now sends them to login. File: `lib/api.js`.
- Checked: UI, and a test (API blocks /me and /refresh).

**28. Landing page oversold the free account**
- Wrong: "With a free account" sat above a list that is mostly paid features.
- Changed: the label is now "Inside the app". File: `pages/Landing.jsx`.

**29. Short-USDT message had no units**
- Changed: it now says "needs 102,272.73 USDT and you have 5,000.00 USDT". File: `crypto/dca.py`.

Also added: a test that walks every `/api/admin/*` route as logged-out (401) and as free, ₹2,000 and trial members (403). All pass. There is also a test that a trial ending drops access.


## Checked and working

- OTP flow:
  - wrong code, 5 tries, then locked out
  - resend cooldown
  - new account vs returning (6 digits auto-submits)
  - `?next=` redirect
  - logout, and session refresh with an expired access cookie
  - invalid numbers
  - UTM capture through to the admin source
- Plan cards show "₹2,000 + GST / month" and "₹2,360 a month incl. 18% GST" (₹5,000 shows ₹5,900).
- Anonymous X-Ray: 1 a day; after the setting change, 2.
- Free 3/3 and ₹2,000 forecast and debate 10/10 limit gates.
- Watchlist star stays after a reload, and the Monday Picks list loads.
- Airdrop ticks stay after a reload.
- Autopilot: KuCoin needs a passphrase; link, plan, pause, resume and delete work.
- Chart Reader: png and jpg work; txt and over 5 MB are refused.
- Ask Deepak:
  - refuses "should I buy"
  - threads work
  - a new KB upload (.txt, .vtt, .md) answers
  - the ASK switch off shows "paused"
- Crash Coach: banner, Ask card and inbox alert after the job.
- Baskets: practice, invest, short USDT and autopilot.
- Checkout (fake): the plan, menu locks and limits change at once.
- Admin:
  - settings take effect (trial days, scenario rates, anonymous checks)
  - grant, trial 0 (drops to the grant) and revoke work
  - Day 3 CSV excludes payers
  - airdrop create, edit and delete work


## Fixed after the QA pass

- **Admin Pulse, Webinar and the Day 3 CSV.** Admin-granted plans now count under their plan, admin logins are left out, and revoked accounts are not on the Day 3 list (`admin/routes.py`, test `tests/test_admin_reports.py`).
- **Paper Money in goal progress** is now labelled "practice only, not real money".
- **Prices** now show "+ GST" (₹2,000 + GST = ₹2,360; ₹5,000 + GST = ₹5,900). Checkout charges the GST-inclusive amount.

## Fixed in the follow-up pass (4 Nov 2026)

Everything that was "found but not fixed" on 3 Nov, plus the problems the load test raised that code can solve.
Tests: `backend/tests/test_followups.py` (23 tests). Backend total: 102 pass. Frontend: `CI=true yarn build` is clean
(lint warnings would fail it). Browser check at 390px and 1280px on the QA server: public page logs no 4xx and no
console errors, logout lands on `/login`, Settings shows field errors and saves nothing, Jobs shows sentences,
airdrop step reorder keeps ids.

**F1. Admin Settings clipped out-of-range numbers without saying so** (31 trial days → 30, crash level 3 dropped)
- Changed: one validation table (`appsettings.SPEC`), served at `GET /admin/settings/spec`. A wrong value is
  refused with `400 bad_setting` and `errors: {field: msg}` ("Trial days must be between 0 days and 30 days (you
  entered 31)."). Nothing is saved if any field is wrong. Also refused now: duplicate crash levels, more than 6
  levels, and rates that don't rise from bad to good. The form uses the same limits and marks each bad field in red.
- Files: `appsettings.py`, `admin/routes.py`, `admin/Settings.jsx`, `components/ui.jsx` (`Field error=`).

**F2. Airdrop step ticks followed the step's position**
- Changed: the admin editor is a list of steps with move up, move down and remove, and each row keeps its step id.
  Pasting several lines splits them into steps. The server checks ids too (`airdrops.reconcile_steps`): a sent id
  is kept, a step without an id takes the id of an old step with the same text, otherwise it gets a new id. Ticks on
  removed steps are deleted, and members only ever see ticks for steps that still exist.
- Files: `features/airdrops.py`, `admin/Airdrops.jsx`.

**F3. Fake AI debate evidence didn't match its points**, and the bear side could have only 2 points (this made
`test_forecast_debate_metered` fail on some dates)
- Changed: each rule creates a `Signal(point, evidence)` together, so a point can't be paired with another point's
  number. There are 3 filler signals per side, so each side always has 3. A live AI reply with fewer than 3
  `{point, evidence}` per side, or an unknown chair verdict, falls back to the rule-based debate.
- File: `features/verdicts.py`.

**F4. Admin › Jobs showed raw JSON**
- Changed: `jobs/summaries.py` turns each job's result into one sentence ("3 plans bought, 1 failed (of 4 due).",
  "BTC is 4.2% below its 30-day high; no crash level reached.", "Skipped: this feature is switched off"). The raw
  values are behind "Details". An unknown job shows "key: value" pairs, never JSON.
- Files: `jobs/summaries.py`, `jobs/registry.py`, `admin/routes.py`, `admin/Jobs.jsx`.

**F5. Autopilot "Run now" only buys plans whose day has come**
- Kept as designed (a new plan buys first on its scheduled day). The job now reports `due` and `next_due_at`, so
  "Run now" with nothing due says "No plans were due. Next buy: 5 Nov 10:00 IST." instead of looking like it did nothing.
- File: `crypto/dca.py`.

**F6. Logout landed on /login?next=<last page>**
- Changed: the auth context records why there is no session: `logout`, `expired` or `revoked`. Log out → `/login`.
  Session ran out mid-use → `/login?next=<page>&reason=expired` with a notice. Account disabled → `/login?reason=revoked`
  with a notice. Same in the admin app.
- Files: `context/AuthContext.jsx`, `components/AppShell.jsx`, `components/AuthShell.jsx`, `pages/Login.jsx`,
  `admin/AdminApp.jsx`, `admin/AdminLogin.jsx`.

**F7. Public pages logged a 401 for /auth/me**
- Changed: new `GET /auth/session`. It always answers 200 (`{user: null, reason}` when logged out) and renews from
  the refresh cookie itself, so page load needs no 401 → refresh → retry round trip. `/auth/me` is unchanged.
- Files: `auth.py`, `context/AuthContext.jsx`, `lib/api.js`.

**F8. Chart Reader "busy" in the hard burst** (116 of 500, load test 3)
- Changed: the AI queue is split into one pool per model class (fast, strong, vision), so a burst of slow chart
  reads can't take the slots X-Ray and Ask need, and the other way round. The vision pool waits up to 45 s, because
  the member is already watching a spinner. A full queue returns `503` with `Retry-After`. The use is refunded, and
  the page retries twice by itself with a countdown ("Lots of people are reading charts right now. Trying again in 12s…").
  Admin › Vendors shows each pool's running, waiting and turned-away counts, refreshed every 10 s.
- Also: the page allowed 8 MB images but the server allows 5 MB. Both say 5 MB now.
- Files: `llm.py`, `features/chart.py`, `features/chart_vision.py`, `admin/routes.py`, `pages/ChartReader.jsx`, `admin/Vendors.jsx`.

**F9. Market data under webinar load** (CoinGecko free tier ~30 calls a minute)
- Changed:
  - Prices are cached per coin, and only the missing coins are fetched, in one call. Before, every different set
    of coins (a plan, a basket, a watchlist) was its own call.
  - Symbol → CoinGecko id lookups are cached for 24 h (1 h for misses).
  - Each worker has its own CoinGecko budget (`COINGECKO_RATE_PER_MIN`). A 429 pauses calls for its `Retry-After`.
    While over budget, the last good value is served and the stale value is never re-stamped as fresh.
- Files: `market/__init__.py`, `market/live.py`, `core/http.py`.

**F10. OTP and alert delivery**
- Changed: one pooled HTTP client per worker (`core/http.shared_client`) for MSG91, AiSensy OTP, WhatsApp alerts
  and CoinGecko, instead of a new TLS connection per call. If WhatsApp OTP fails 5 times in a row (for example
  AiSensy's burst limit), it is skipped for 60 s and codes go straight to SMS. An explicit "Send by SMS / WhatsApp"
  choice is always tried.
- Files: `core/http.py`, `accounts/otp_service.py`, `accounts/otp_providers.py`, `notify/channels.py`.

## Still to check live (needs real accounts, can't be tested here)

- **Anthropic rate limits:** pool size × `WEB_CONCURRENCY` must fit the account. Watch "Turned away" in Admin › Vendors during the webinar.
- **CoinGecko paid key:** set `COINGECKO_API_KEY`, `COINGECKO_BASE_URL` and `COINGECKO_RATE_PER_MIN` (for example 400).
- **MSG91 / AiSensy burst limits:** confirm 500 codes a minute with each vendor.
- **Harmless, left as is:** the fake AI's wording in QA mode is canned sample text.
