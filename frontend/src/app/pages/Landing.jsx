// "/" — the free open page: hero, three free tools (What If, Coin X-Ray, Market Pulse),
// what you get with an account, plans preview, create-account CTA.
import { Link } from "react-router-dom";
import {
  ArrowLeftRight, CalendarDays, CandlestickChart, Gift, Layers, MessageCircle, Newspaper, Radar, Repeat, ScanSearch, Scale, Target,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import brand from "@/brand";
import PublicLayout from "../components/PublicLayout";
import WhatIf from "../components/WhatIf";
import XrayBox from "../components/Xray";
import PulseStrip from "../components/Pulse";
import { PlanCard, usePlansCatalog } from "../components/PlansView";
import { LogoMark } from "../components/Logo";
import { Card, Label, LinkButton } from "../components/ui";

const GET = [
  { icon: ScanSearch, t: "Coin X-Ray", d: "Check any coin, link or WhatsApp tip before you put money in." },
  { icon: Scale, t: "Daily Verdicts", d: "Bullish, Neutral or Bearish on the top coins, every morning, with reasons." },
  { icon: Target, t: "My Crypto Plan", d: "Your goal in rupees, a monthly plan, and ₹1,00,000 of practice money." },
  { icon: Repeat, t: "SIP Autopilot", d: "Buy Bitcoin every month from your own exchange, automatically." },
  { icon: Gift, t: "Airdrop Finder", d: "Free-token airdrops, each checked for scams, with simple steps." },
  { icon: CandlestickChart, t: "Chart Reader", d: "Send a chart screenshot, get the trend and the levels to watch." },
  { icon: MessageCircle, t: `Ask ${brand.coach} AI`, d: `Any crypto question, answered in ${brand.coach}'s teaching style.` },
  { icon: Layers, t: "Crypto Baskets", d: "Ready-made groups of coins you can practise, buy or auto-buy." },
  { icon: Radar, t: "Early Coin Radar", d: "New and trending coins, auto-checked for red flags." },
  { icon: CalendarDays, t: "Events Calendar", d: "Unlocks, listings and big dates that move prices." },
  { icon: ArrowLeftRight, t: "P2P Rate Finder", d: "The best rupee-to-USDT rates, with safer sellers marked." },
  { icon: Newspaper, t: "News Decoder", d: "Crypto news in plain words and what it means for you." },
];

function ToolCard({ n, title, sub, children, id }) {
  return (
    <section id={id} className="rounded-bzcard border border-bz-line bg-bz-card shadow-bzframe p-5 sm:p-6 scroll-mt-20">
      <div className="flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-full bg-bz-gold text-white grid place-items-center font-bzmono text-[12px] font-semibold" aria-hidden>{n}</span>
        <span className="font-bzmono text-[11px] uppercase tracking-[0.2em] text-bz-gold-deep">Free tool</span>
      </div>
      <h2 className="font-bzserif text-[26px] sm:text-[30px] font-semibold leading-tight mt-3">{title}</h2>
      {sub && <p className="text-[15px] text-bz-muted mt-1.5">{sub}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

export default function Landing() {
  const { user } = useAuth();
  const cat = usePlansCatalog();
  const plans = cat.data?.plans || [];
  const cta = user ? "/app" : "/login";
  const ctaLabel = user ? "Open the app" : "Create free account";
  return (
    <PublicLayout wide>
      {/* Hero */}
      <section className="border-b border-bz-line bg-bz-panel">
        <div className="mx-auto max-w-[1120px] px-4 md:px-8 py-10 sm:py-14">
          <div className="flex items-center gap-3">
            <LogoMark size={40} />
            <span className="font-bzmono text-[11px] tracking-[0.28em] uppercase"><span className="text-bz-gold-deep">{brand.name}</span><span className="text-bz-muted">_{brand.tagline}</span></span>
          </div>
          <h1 className="font-bzserif mt-6 text-[36px] sm:text-[52px] lg:text-[60px] font-semibold leading-[1.04] tracking-[-0.01em] max-w-[820px]">
            Crypto, made simple <span className="text-bz-accent">and safer.</span>
          </h1>
          <p className="mt-4 text-[17px] sm:text-[19px] leading-relaxed text-bz-muted max-w-[680px]">
            Check any coin or tip for scams, see a daily call on the top coins, and build a simple crypto plan in rupees. Three tools below are free, no login.
          </p>
          <div className="mt-6 flex flex-col sm:flex-row gap-2.5">
            <LinkButton to={cta} className="sm:w-auto" data-testid="hero-cta">{ctaLabel}</LinkButton>
            <a href="#xray" className="inline-flex items-center justify-center min-h-[48px] px-5 rounded-bzbtn border border-bz-line-strong font-bzmono text-[12px] uppercase tracking-[0.16em] hover:bg-bz-inset">Check a coin now</a>
          </div>
        </div>
      </section>

      {/* Three free tools */}
      <div className="mx-auto max-w-[1120px] px-4 md:px-8 py-8 sm:py-12 space-y-5">
        <ToolCard n="1" id="pulse" title="Market Pulse" sub="Today's prices, the mood of the market, and where Bitcoin is in its 4-year cycle.">
          <PulseStrip />
        </ToolCard>
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          <ToolCard n="2" id="whatif" title="What If?" sub="If you had put a fixed amount into crypto every month, what would it be worth today?">
            <WhatIf />
          </ToolCard>
          <ToolCard n="3" id="xray" title="Coin X-Ray" sub="Got a tip on WhatsApp? A new coin from a friend? Check it before you pay.">
            <XrayBox />
          </ToolCard>
        </div>
      </div>

      {/* What you get */}
      <section className="border-y border-bz-line bg-bz-panel">
        <div className="mx-auto max-w-[1120px] px-4 md:px-8 py-10 sm:py-14">
          <Label>Inside the app</Label>
          <h2 className="font-bzserif text-[30px] sm:text-[40px] font-semibold leading-tight">What you get <span className="text-bz-accent">inside the app</span></h2>
          <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {GET.map(({ icon: Icon, t, d }) => (
              <li key={t} className="flex gap-3 rounded-bzcard border border-bz-line bg-bz-card p-4">
                <Icon className="w-6 h-6 text-bz-gold shrink-0" strokeWidth={1.75} aria-hidden />
                <span className="min-w-0"><span className="block font-semibold text-[15.5px]">{t}</span><span className="block text-[14px] text-bz-muted mt-0.5">{d}</span></span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Plans preview */}
      <section className="mx-auto max-w-[1120px] px-4 md:px-8 py-10 sm:py-14">
        <Label>Plans</Label>
        <h2 className="font-bzserif text-[30px] sm:text-[40px] font-semibold leading-tight">Start free. <span className="text-bz-accent">Upgrade when you're ready.</span></h2>
        {cat.data?.trial_days ? <p className="text-[16px] text-bz-muted mt-2">New accounts get {cat.data.trial_days} days of everything, free.</p> : null}
        {plans.length > 0 && (
          <div className="mt-6 grid gap-3 md:grid-cols-3">
            {plans.map((p) => <PlanCard key={p.id} p={p} highlight={p.id === "lite"} />)}
          </div>
        )}
        <Link to="/plans" className="inline-block mt-4 text-[15px] font-semibold text-bz-accent">See plan details</Link>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-[1120px] px-4 md:px-8 pb-14">
        <Card className="text-center py-10 border-bz-gold">
          <h2 className="font-bzserif text-[28px] sm:text-[36px] font-semibold leading-tight">Your crypto co-pilot is <span className="text-bz-gold">one tap away.</span></h2>
          <p className="text-[16px] text-bz-muted mt-2">Log in with your mobile number. No password, no card.</p>
          <LinkButton to={cta} className="mt-6 w-full sm:w-auto sm:px-10 text-[13px]" data-testid="bottom-cta">{ctaLabel}</LinkButton>
        </Card>
      </section>
    </PublicLayout>
  );
}
