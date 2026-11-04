# Coinzeye web (frontend)

React app for **Coinzeye** (working name): the free public page, the member app and the admin panel.
Sibling of Bullzeye, same look (Inter / Fraunces / JetBrains Mono, 16px cards, mono labels), new colours.

Stack: Create React App + craco, Tailwind 3, react-router 7, @tanstack/react-query 5, axios, recharts 3, lucide-react.
The API it talks to is described in `../docs/API_CONTRACT.md`.

## Run

```bash
yarn install
yarn start                 # http://localhost:3000, proxies /api → http://localhost:8001
CI=false yarn build        # production build in build/ (the backend can serve it)
```

## Environment

| Variable | Default | What it does |
|---|---|---|
| `REACT_APP_BACKEND_URL` | empty | Only when the API is on another host. Requests go to `${REACT_APP_BACKEND_URL}/api` with cookies (`withCredentials`). |
| `DEV_API_TARGET` | `http://localhost:8001` | `yarn start` only: where the dev server proxies `/api`. |

## Where the brand lives

- **Name, tagline, short name, coach name:** `src/brand.js`. Every screen reads it from there.
  Two static copies exist for the browser itself: `<title>` in `public/index.html` and `name` in `public/manifest.json`. Change them too when the name changes.
- **Colours:** `src/index.css` → the `--bz-*` tokens for light (`:root, [data-theme="light"]`) and dark (`[data-theme="dark"]`).
  Token names are kept from Bullzeye. Green (`accent`) = up / bullish / buttons, red (`miss`) = down / bearish, orange (`gold`) = brand marker, active menu item, highlights.
  `tailwind.config.js` maps them to classes like `bg-bz-card`, `text-bz-accent`.
- **Logo:** `public/logo.svg` (also `public/favicon.svg`), an original orange coin with an eye / target mark.

## Routes

Public (no login)

| Path | Screen |
|---|---|
| `/` | Free page: hero, Market Pulse, What If, Coin X-Ray, what you get, plans preview, create-account CTA |
| `/login` | Mobile OTP login / sign-up (`?next=` respected) |
| `/plans` | Pricing |
| `/terms`, `/privacy`, `/disclosures` | Placeholder legal pages |

Member app (login required; logged out → `/login?next=…`)

| Path | Screen | Feature key |
|---|---|---|
| `/app` | Today | — |
| `/app/xray` | Coin X-Ray + history | `xray` |
| `/app/verdicts` | Daily verdicts, Market Pulse, Monday Picks | `verdicts` |
| `/app/coin/:symbol` | Coin page: verdict, history, Forecast, Debate | `verdicts` (+ `forecast`, `debate`) |
| `/app/plan` | My Crypto Plan, Paper Money, real portfolio | `plan` |
| `/app/airdrops` | Airdrop Finder | `airdrops` |
| `/app/autopilot` | SIP Autopilot | `autopilot` |
| `/app/chart` | Chart Reader | `chart` |
| `/app/ask` | Ask Deepak AI | `ask` |
| `/app/baskets` | Crypto Baskets | `baskets` |
| `/app/radar` | Early Coin Radar | `radar` |
| `/app/calendar` | Events Calendar | `calendar` |
| `/app/p2p` | P2P Rate Finder | `p2p` |
| `/app/news` | News Decoder | `news` |
| `/app/inbox` | Alerts | — |
| `/app/account` | Profile, plan, usage, cancel, theme, log out | — |
| `/app/plans` | Pricing inside the app | — |

Admin (`role: admin`; logged out → `/admin/login`, staff email + password or phone OTP)

`/admin` Pulse · `/admin/webinar` · `/admin/users` · `/admin/airdrops` · `/admin/baskets` · `/admin/events` · `/admin/picks` ·
`/admin/crash-notes` · `/admin/kb` · `/admin/etf-flows` · `/admin/features` · `/admin/settings` · `/admin/vendors` · `/admin/jobs`

## How gating works

- `/auth/me` returns `plan.features`. A page whose feature is off shows a **LockCard** (`src/app/components/common.jsx`: what it does,
  which plan includes it, Upgrade). Menu items for locked features stay visible with a small lock.
- Any API answer `403 {code: "locked"}` or `402 {code: "limit"}` opens the same card in a sheet (`GateSheet.jsx`).
  Screens that show the card inline pass `{ _silentGate: true }` on the request.
- On `401` the axios instance calls `POST /auth/refresh` once and retries; if that fails the user is sent to login.

## Code layout

```
src/
  brand.js                 product name (one place)
  index.css                theme tokens
  App.js                   routes
  lib/                     api (axios), format (₹ en-IN, dates), attribution (utm, events), checkout, features
  context/                 AuthContext (user + PlanInfo), ThemeContext (light/dark)
  app/components/          shared UI (ui.jsx, common.jsx), AppShell, X-Ray, What If, Pulse, plan/*, Dca …
  app/pages/               one file per page
  app/admin/               admin panel, one file per page + shared.jsx
```

Browser storage is used only for the theme (`cz_theme`), first-landing attribution (`cz_attr`) and a device id (`cz_device`), all wrapped in try/catch.
