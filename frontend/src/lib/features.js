// Feature keys (API_CONTRACT.md) with the plain-English copy used on lock cards and in the menu.
import brand from "@/brand";

export const PLAN_LABEL = { free: "Free", lite: "₹2,000 plan", pro: "₹5,000 plan" };
export const PLAN_PRICE = { free: 0, lite: 2000, pro: 5000 };

export const FEATURES = {
  whatif: { name: "What If calculator", what: "See what a monthly amount in Bitcoin, Ethereum or Solana would be worth today.", plan: "free" },
  xray: { name: "Coin X-Ray", what: "Paste any coin, link or WhatsApp tip and get a plain safe / risky / likely-scam answer.", plan: "free" },
  verdicts: { name: "Daily Verdicts", what: "A Bullish, Neutral or Bearish call on the top coins every morning.", plan: "free" },
  verdict_details: { name: "Verdict reasons", what: "The bull points, bear points and the chair's call behind every verdict.", plan: "lite" },
  forecast: { name: "Price Forecast", what: "Where a coin's price could go in the next 7 or 30 days, with a low–high range.", plan: "lite" },
  debate: { name: "Bull vs Bear Debate", what: "Two AI analysts argue for and against a coin, then a chair makes the call.", plan: "lite" },
  pulse: { name: "Market Pulse", what: "Prices, Fear & Greed, ETF flows and where we are in the Bitcoin cycle.", plan: "lite" },
  watchlist: { name: "Watchlist", what: "Star coins and get an alert when their verdict changes.", plan: "lite" },
  monday_picks: { name: "Monday Picks", what: "Two coins picked every Monday, with the reasoning in plain words.", plan: "lite" },
  plan: { name: "My Crypto Plan", what: "Turn a goal into a monthly plan in rupees, with bad, average and good outcomes.", plan: "free" },
  paper_trade: { name: "Paper Money trading", what: "Buy and sell with ₹1,00,000 of practice money before you use real money.", plan: "lite" },
  airdrops: { name: "Airdrop Finder", what: "Live free-token airdrops, each checked for scams, with a step-by-step checklist.", plan: "lite" },
  autopilot: { name: "SIP Autopilot", what: "Buy crypto every week or month automatically from your own exchange account.", plan: "lite" },
  chart: { name: "Chart Reader", what: "Upload a chart screenshot and get the trend, support, resistance and what to watch.", plan: "lite" },
  ask: { name: `Ask ${brand.coach} AI`, what: `Ask anything about crypto and get an answer in ${brand.coach}'s teaching style, from his own sessions.`, plan: "pro" },
  baskets: { name: "Crypto Baskets", what: "Ready-made groups of coins by theme. Practise, buy once, or set a monthly autopilot.", plan: "pro" },
  radar: { name: "Early Coin Radar", what: "New listings and trending coins, each auto-checked by Coin X-Ray.", plan: "pro" },
  calendar: { name: "Events Calendar", what: "Token unlocks, listings, upgrades and big economy dates that move prices.", plan: "pro" },
  p2p: { name: "P2P Rate Finder", what: "The best rupee-to-USDT P2P rates right now, with safer sellers marked.", plan: "pro" },
  news: { name: "News Decoder", what: "Crypto news in plain words: what happened and what it means for you.", plan: "pro" },
};

export const featureInfo = (key) => FEATURES[key] || { name: "This feature", what: "", plan: "lite" };
