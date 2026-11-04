// /app — Today. The member's home after the webinar: where Bitcoin is in its 4-year cycle (the one bold element),
// how the market feels today, their goal, and what changed since yesterday.
//
// Layout (left aligned):
//   date + greeting
//   crash notice (only during a fall)
//   cycle dial panel                       ← components/CycleDial.jsx
//   market strip                           ← components/Pulse.jsx MarketStrip
//   your goal (wide) | what changed (verdicts, radar, inbox)
//   tools list (phone only: the sidebar lists the same tools on a computer)
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronRight, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth, useFeature } from "@/context/AuthContext";
import { inr, istHour, istLongToday, venueName } from "@/lib/format";
import { NAV_MAIN, NAV_PRO } from "../components/AppShell";
import CycleDial from "../components/CycleDial";
import { MarketStrip, usePulse } from "../components/Pulse";
import { ErrorCard, LinkButton, Skeleton } from "../components/ui";
import { VerdictChip, XrayChip } from "../components/common";

function greeting() {
  const h = istHour();
  return h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

// A quiet surface for a group of related things. Radius sits between the hero (28) and inputs (12).
function Group({ title, action, children, className = "", testid }) {
  return (
    <section className={`rounded-bzcard bg-bz-card border border-bz-line px-5 py-4 ${className}`} data-testid={testid}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-bzdisplay text-[20px] font-bold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

const linkCls = "text-[15px] font-semibold text-bz-ink underline decoration-bz-gold decoration-2 underline-offset-4 hover:decoration-bz-ink";

function CrashNotice({ crash }) {
  if (!crash?.active) return null;
  const fall = crash.drawdown_pct != null ? `${Math.abs(Number(crash.drawdown_pct)).toFixed(0)}%` : "sharply";
  return (
    <section className="rounded-bzcard border-2 border-bz-miss bg-bz-miss-tint px-5 py-4 flex gap-3" data-testid="crash-banner" role="status">
      <AlertTriangle className="w-6 h-6 text-bz-miss shrink-0 mt-0.5" aria-hidden />
      <div className="min-w-0">
        <p className="font-bzdisplay text-[20px] font-bold leading-tight">Bitcoin is down {fall} from its 30-day high</p>
        {crash.note && <p className="text-[16px] mt-1 max-w-[65ch]">{crash.note}</p>}
        <Link to="/app/ask" className={`inline-block mt-2 ${linkCls}`}>Talk it through with the coach</Link>
      </div>
    </section>
  );
}

function GoalGroup({ goal, plan }) {
  const g = goal || (plan ? {
    name: plan.goal_name, target_inr: plan.target_inr, value_inr: plan.goal_progress?.value_inr,
    pct: plan.goal_progress?.pct, source: plan.goal_progress?.source,
  } : null);
  if (!g) {
    return (
      <Group title="Your goal" className="md:col-span-7">
        <p className="text-[16px] mt-2 max-w-[48ch]">Pick a goal in rupees, like a down payment or 1 Bitcoin, and get a simple monthly plan. You also get ₹1,00,000 of practice money to try it.</p>
        <LinkButton to="/app/plan" className="mt-4 w-full sm:w-auto">Make my plan</LinkButton>
      </Group>
    );
  }
  const p = Math.max(0, Math.min(100, Number(g.pct) || 0));
  return (
    <Group title="Your goal" className="md:col-span-7" testid="goal-card" action={<Link to="/app/plan" className={linkCls}>Open plan</Link>}>
      <p className="text-[16px] text-bz-muted mt-1">{g.name || "My goal"}</p>
      <p className="mt-3 flex items-baseline gap-2 flex-wrap">
        <span className="font-bzdisplay text-[39px] font-bold leading-none tabular">{inr(g.value_inr || 0)}</span>
        <span className="text-[16px] text-bz-muted">of {inr(g.target_inr)}</span>
      </p>
      <div className="relative h-3 rounded-full bg-bz-inset mt-4 overflow-hidden" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p} aria-label="Goal progress">
        <span className="absolute inset-y-0 left-0 rounded-full bg-bz-gold" style={{ width: `${Math.max(p, 2)}%` }} />
      </div>
      <p className="text-[14px] mt-2"><b className="tabular">{p.toFixed(0)}%</b> <span className="text-bz-muted">of the way there.</span></p>
      <p className="text-[13px] text-bz-muted mt-3 max-w-[60ch]">
        {g.source === "portfolio" ? "Counted from your linked exchange." : g.source === "paper" ? "Practice only: this is your Paper Money, not real money. Link an exchange to track the real thing." : "Start Paper Money or link an exchange to track it."}
      </p>
    </Group>
  );
}

function Row({ to, title, sub, right }) {
  return (
    <li>
      <Link to={to} className="flex items-center justify-between gap-3 py-3 min-h-[56px] hover:bg-bz-inset -mx-2 px-2 rounded-bzbtn">
        <span className="min-w-0">
          <span className="block font-semibold text-[16px] truncate">{title}</span>
          {sub && <span className="block text-[14px] text-bz-muted truncate">{sub}</span>}
        </span>
        {right}
      </Link>
    </li>
  );
}

function WhatChanged({ canRadar, unread }) {
  const verdicts = useQuery({ queryKey: ["verdicts-today"], queryFn: async () => (await api.get("/verdicts/today")).data });
  const radar = useQuery({ queryKey: ["radar"], queryFn: async () => (await api.get("/radar", { _silentGate: true })).data, enabled: canRadar });
  const changed = (verdicts.data?.coins || []).filter((c) => c.changed_from);
  const fresh = (radar.data?.items || []).slice(0, 3);
  return (
    <Group title="What changed" className="md:col-span-5" testid="what-changed">
      {verdicts.isLoading ? <Skeleton lines={3} className="mt-3" /> : (
        <ul className="mt-1 divide-y divide-bz-line">
          {unread > 0 && (
            <Row to="/app/inbox" title={`${unread} new alert${unread === 1 ? "" : "s"}`} sub="In your inbox"
              right={<span className="w-2.5 h-2.5 rounded-full bg-bz-gold shrink-0" aria-hidden />} />
          )}
          {changed.map((c) => (
            <Row key={c.symbol} to={`/app/coin/${c.symbol}`} title={`${c.name || c.symbol} is now ${String(c.verdict || "").toLowerCase()}`}
              sub={`Was ${String(c.changed_from).toLowerCase()} yesterday`} right={<VerdictChip v={c.verdict} conf={c.confidence} />} />
          ))}
          {changed.length === 0 && !verdicts.isError && (
            <Row to="/app/verdicts" title="No verdict changed today" sub="See the daily call on the top 10 coins" right={<ChevronRight className="w-5 h-5 text-bz-muted" aria-hidden />} />
          )}
          {canRadar && fresh.map((r) => (
            <Row key={r.id || r.symbol} to="/app/radar" title={`${r.name || r.symbol} ${r.kind === "new_listing" ? "listed" : "is trending"}`}
              sub={r.kind === "new_listing" && r.venue ? `New on ${venueName(r.venue).replace(" · ", " and ")}` : "On the Early Coin Radar"}
              right={r.xray ? <XrayChip label={r.xray.label} /> : null} />
          ))}
        </ul>
      )}
      {!canRadar && (
        <p className="text-[14px] text-bz-muted mt-3 pt-3 border-t border-bz-line">
          New listings and trending coins show up here on the ₹5,000 plan. <Link to="/app/plans" className={linkCls}>See plans</Link>
        </p>
      )}
    </Group>
  );
}

// Phone only. A plain list, split into what's open on your plan and what isn't, instead of 13 identical cards.
function Tools() {
  const { user, plan } = useAuth();
  const admin = user?.role === "admin";
  const all = [...NAV_MAIN.slice(1), ...NAV_PRO];
  const isLocked = (f) => f && !admin && !plan?.features?.[f];
  const open = all.filter((t) => !isLocked(t.feature));
  const locked = all.filter((t) => isLocked(t.feature));
  const list = (items) => (
    <ul className="divide-y divide-bz-line">
      {items.map(({ to, key, label, sub, icon: Icon, feature }) => (
        <li key={to}>
          <Link to={to} data-testid={`tile-${key}`} className="flex items-center gap-3 py-3 min-h-[56px]">
            <span className="w-10 h-10 rounded-full bg-bz-gold-tint grid place-items-center shrink-0"><Icon className="w-5 h-5 text-bz-gold-deep" strokeWidth={1.9} aria-hidden /></span>
            <span className="min-w-0 flex-1">
              <span className="block font-semibold text-[16px]">{label}</span>
              <span className="block text-[14px] text-bz-muted truncate">{sub}</span>
            </span>
            {isLocked(feature) ? <Lock className="w-4 h-4 text-bz-muted" aria-label="Not on your plan" /> : <ChevronRight className="w-5 h-5 text-bz-muted" aria-hidden />}
          </Link>
        </li>
      ))}
    </ul>
  );
  return (
    <section className="lg:hidden" aria-labelledby="tools-title">
      <h2 id="tools-title" className="font-bzdisplay text-[20px] font-bold">Your tools</h2>
      {list(open)}
      {locked.length > 0 && (
        <>
          <h3 className="text-[14px] font-semibold text-bz-muted mt-5">On a bigger plan</h3>
          {list(locked)}
        </>
      )}
    </section>
  );
}

export default function Today() {
  const { user } = useAuth();
  const canAsk = useFeature("ask");
  const canRadar = useFeature("radar");
  const pulse = usePulse();
  const coach = useQuery({ queryKey: ["coach"], queryFn: async () => (await api.get("/ask/coach", { _silentGate: true })).data, enabled: canAsk });
  const plans = useQuery({ queryKey: ["plans"], queryFn: async () => (await api.get("/plan", { _silentGate: true })).data });
  const inbox = useQuery({ queryKey: ["inbox"], queryFn: async () => (await api.get("/inbox")).data, staleTime: 60_000 });
  const first = (plans.data?.plans || [])[0];
  const firstName = (user?.name || "").split(" ")[0];
  return (
    <div className="space-y-5 md:space-y-6">
      <header>
        <p className="text-[16px] text-bz-muted">{istLongToday()}</p>
        <h1 className="font-bzdisplay text-[39px] sm:text-[49px] font-bold leading-[1.02] tracking-[-0.01em] mt-0.5">
          {greeting()}{firstName ? `, ${firstName}` : ""}
        </h1>
      </header>

      <CrashNotice crash={coach.data?.crash} />

      {pulse.isLoading ? (
        <div className="rounded-bzhero bg-bz-hero p-8"><div className="skeleton h-40 opacity-30" /></div>
      ) : pulse.isError ? (
        <ErrorCard error={pulse.error} onRetry={() => pulse.refetch()} what="market data" />
      ) : (
        <>
          <CycleDial cycle={pulse.data?.cycle} />
          <MarketStrip pulse={pulse.data} />
        </>
      )}

      <div className="grid gap-5 md:gap-6 md:grid-cols-12 items-start">
        {plans.isLoading && !coach.data
          ? <section className="md:col-span-7 rounded-bzcard bg-bz-card border border-bz-line p-5"><Skeleton lines={3} /></section>
          : <GoalGroup goal={coach.data?.goal} plan={first} />}
        <WhatChanged canRadar={canRadar} unread={inbox.data?.unread || 0} />
      </div>

      <Tools />
    </div>
  );
}
