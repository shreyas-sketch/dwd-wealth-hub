// "/" — the free open page people reach from the webinar QR code.
//
// They arrive holding a question ("is this coin / this tip safe?"), so the hero IS the tool: the live Coin X-Ray
// sits on the indigo panel next to the headline. Then the two other free tools (What If, Market today), what each
// plan adds (grouped, because the grouping is the information), the plan cards, and one closing call to action.
// The halving dial stays the signature of the logged-in Today screen, so each screen spends its boldness once.
import { Link } from "react-router-dom";
import {
  ArrowLeftRight, CalendarDays, CandlestickChart, Gift, Layers, MessageCircle, Newspaper, Radar, Repeat, ScanSearch, Scale, Target,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import brand from "@/brand";
import PublicLayout from "../components/PublicLayout";
import WhatIf from "../components/WhatIf";
import XrayBox from "../components/Xray";
import { CycleMeter, MarketStrip, usePulse } from "../components/Pulse";
import { PlanCard, usePlansCatalog } from "../components/PlansView";
import { ErrorCard, LinkButton, Skeleton } from "../components/ui";

const TIERS = [
  {
    name: "On every account, free",
    items: [
      { icon: ScanSearch, t: "Coin X-Ray", d: "Check any coin, link or WhatsApp tip before you put money in." },
      { icon: Scale, t: "Daily Verdicts", d: "Bullish, Neutral or Bearish on the top 10 coins every morning, with reasons." },
      { icon: Target, t: "My Crypto Plan", d: "Your goal in rupees, a monthly plan, and ₹1,00,000 of practice money." },
    ],
  },
  {
    name: "The ₹2,000 plan adds",
    items: [
      { icon: Repeat, t: "SIP Autopilot", d: "Buys Bitcoin every month from your own exchange account." },
      { icon: Gift, t: "Airdrop Finder", d: "Free-token airdrops, each checked for scams, with simple steps." },
      { icon: CandlestickChart, t: "Chart Reader", d: "Send a chart screenshot, get the trend and the levels to watch." },
    ],
  },
  {
    name: "The ₹5,000 plan adds",
    items: [
      { icon: MessageCircle, t: `Ask ${brand.coach} AI`, d: `Any crypto question, answered the way ${brand.coach} teaches.` },
      { icon: Layers, t: "Crypto Baskets", d: "Ready-made groups of coins to practise with, buy or auto-buy." },
      { icon: Radar, t: "Early Coin Radar", d: "New and trending coins, checked for red flags automatically." },
      { icon: CalendarDays, t: "Events Calendar", d: "Unlocks, listings and other dates that move prices." },
      { icon: ArrowLeftRight, t: "P2P Rate Finder", d: "The best rupee-to-USDT rates, with safer sellers marked." },
      { icon: Newspaper, t: "News Decoder", d: "Crypto news in plain words, and what it means for you." },
    ],
  },
];

const wrap = "mx-auto max-w-[1120px] px-4 md:px-8";

function SectionHead({ title, sub }) {
  return (
    <div className="max-w-[640px]">
      <h2 className="font-bzdisplay text-[31px] sm:text-[39px] font-bold leading-[1.08]">{title}</h2>
      {sub && <p className="text-[17px] text-bz-muted mt-2 leading-relaxed">{sub}</p>}
    </div>
  );
}

function Market() {
  const q = usePulse();
  if (q.isLoading) return <Skeleton lines={4} />;
  if (q.isError) return <ErrorCard error={q.error} onRetry={() => q.refetch()} what="market prices" />;
  return (
    <div className="space-y-4">
      <MarketStrip pulse={q.data} />
      <CycleMeter cycle={q.data?.cycle} />
    </div>
  );
}

export default function Landing() {
  const { user } = useAuth();
  const cat = usePlansCatalog();
  const plans = cat.data?.plans || [];
  const cta = user ? "/app" : "/login";
  const ctaLabel = user ? "Open the app" : "Create a free account";
  return (
    <PublicLayout wide>
      {/* Hero: the tool people came for */}
      <div className={`${wrap} pt-5 sm:pt-8`}>
        <section className="rounded-bzhero bg-bz-hero text-bz-hero-ink px-5 py-7 sm:px-10 sm:py-10 grid gap-8 lg:grid-cols-[1fr_minmax(0,480px)] lg:items-start" aria-labelledby="hero-title">
          <div className="lg:pt-4">
            <h1 id="hero-title" className="font-bzdisplay text-[39px] sm:text-[49px] lg:text-[61px] font-bold leading-[1.02] tracking-[-0.01em] max-w-[13ch]">
              Check a crypto tip before you pay.
            </h1>
            <p className="mt-4 text-[17px] sm:text-[19px] leading-relaxed text-bz-hero-muted max-w-[46ch]">
              Paste a coin name, a link or the WhatsApp message you got. In a few seconds you'll know if it looks safe, risky or like a scam. Free, no login.
            </p>
            <ul className="mt-6 space-y-2 text-[16px] text-bz-hero-muted">
              <li><a href="#whatif" className="text-bz-hero-ink font-semibold underline decoration-bz-gold decoration-2 underline-offset-4">What would ₹1,000 a month have become?</a></li>
              <li><a href="#market" className="text-bz-hero-ink font-semibold underline decoration-bz-gold decoration-2 underline-offset-4">Where is Bitcoin in its 4-year cycle?</a></li>
            </ul>
          </div>
          <div id="xray" className="rounded-bzcard bg-bz-card text-bz-ink p-5 sm:p-6 scroll-mt-20">
            <XrayBox />
          </div>
        </section>
      </div>

      <div className={`${wrap} py-12 sm:py-16 space-y-14 sm:space-y-20`}>
        <section id="whatif" className="scroll-mt-20 grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr] lg:gap-12" aria-labelledby="whatif-title">
          <div>
            <h2 id="whatif-title" className="font-bzdisplay text-[31px] sm:text-[39px] font-bold leading-[1.08]">What if you'd started earlier?</h2>
            <p className="text-[17px] text-bz-muted mt-2 leading-relaxed">Pick a monthly amount and a coin. See what buying every month would be worth today, including the worst time you could have started.</p>
          </div>
          <div className="rounded-bzcard bg-bz-card border border-bz-line p-5 sm:p-6 min-w-0"><WhatIf /></div>
        </section>

        <section id="market" className="scroll-mt-20 space-y-6" aria-labelledby="market-title-landing">
          <SectionHead title="The market right now" sub="Today's prices in rupees, the market's mood, and where Bitcoin is in its 4-year halving cycle." />
          <h2 id="market-title-landing" className="sr-only">Market today</h2>
          <Market />
        </section>

        <section aria-labelledby="inside-title">
          <h2 id="inside-title" className="font-bzdisplay text-[31px] sm:text-[39px] font-bold leading-[1.08] max-w-[640px]">What you get with an account</h2>
          {cat.data?.trial_days ? <p className="text-[17px] text-bz-muted mt-2">New accounts get every tool free for {cat.data.trial_days} days.</p> : null}
          <div className="mt-8 grid gap-8 lg:grid-cols-3">
            {TIERS.map((tier) => (
              <div key={tier.name}>
                <h3 className="text-[16px] font-semibold text-bz-gold-deep pb-2 border-b-2 border-bz-gold">{tier.name}</h3>
                <ul className="divide-y divide-bz-line">
                  {tier.items.map(({ icon: Icon, t, d }) => (
                    <li key={t} className="flex gap-3 py-3.5">
                      <span className="w-10 h-10 rounded-full bg-bz-gold-tint grid place-items-center shrink-0"><Icon className="w-5 h-5 text-bz-gold-deep" strokeWidth={1.9} aria-hidden /></span>
                      <span className="min-w-0"><span className="block font-semibold text-[16px]">{t}</span><span className="block text-[15px] text-bz-muted leading-snug mt-0.5">{d}</span></span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="plans-title">
          <h2 id="plans-title" className="font-bzdisplay text-[31px] sm:text-[39px] font-bold leading-[1.08]">Start free. Upgrade when you're ready.</h2>
          {plans.length > 0 && (
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {plans.map((p) => <PlanCard key={p.id} p={p} highlight={p.id === "lite"} />)}
            </div>
          )}
          <Link to="/plans" className="inline-block mt-5 text-[16px] font-semibold underline decoration-bz-gold decoration-2 underline-offset-4">Compare the plans in detail</Link>
        </section>

        <section className="border-t-2 border-bz-ink pt-8 grid gap-5 md:grid-cols-[1fr_auto] md:items-end" aria-labelledby="cta-title">
          <div>
            <h2 id="cta-title" className="font-bzdisplay text-[31px] sm:text-[39px] font-bold leading-[1.08]">Log in with your mobile number.</h2>
            <p className="text-[17px] text-bz-muted mt-2">No password and no card. You get a code on WhatsApp or SMS.</p>
          </div>
          <LinkButton to={cta} className="w-full md:w-auto md:px-10" data-testid="bottom-cta">{ctaLabel}</LinkButton>
        </section>
      </div>
    </PublicLayout>
  );
}
