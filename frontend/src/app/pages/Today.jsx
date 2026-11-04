// /app — Today: market pulse + cycle meter, crash coach banner, goal progress, verdict changes,
// latest radar items (₹5,000 plan), inbox count, quick tiles to every feature.
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bell, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth, useFeature } from "@/context/AuthContext";
import { inr, istHour, istToday, sdate, venueName } from "@/lib/format";
import { NAV_MAIN, NAV_PRO } from "../components/AppShell";
import PulseStrip from "../components/Pulse";
import { Card, Chip, Label, LinkButton, Meter, Skeleton } from "../components/ui";
import { Move, VerdictChip, XrayChip } from "../components/common";

function greeting() {
  const h = istHour();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function CrashBanner({ crash }) {
  if (!crash?.active) return null;
  return (
    <Card className="border-bz-miss bg-bz-miss-tint" data-testid="crash-banner">
      <div className="flex gap-3">
        <AlertTriangle className="w-6 h-6 text-bz-miss shrink-0" aria-hidden />
        <div className="min-w-0">
          <p className="font-semibold text-[16px]">Bitcoin is down {crash.drawdown_pct != null ? `${Math.abs(Number(crash.drawdown_pct)).toFixed(0)}%` : "sharply"} from its 30-day high.</p>
          {crash.note && <p className="text-[15px] mt-1">{crash.note}</p>}
          <Link to="/app/ask" className="inline-block mt-2 text-sm font-semibold text-bz-accent">Talk it through with the coach</Link>
        </div>
      </div>
    </Card>
  );
}

function GoalCard({ goal, plan }) {
  const g = goal || (plan ? {
    name: plan.goal_name, target_inr: plan.target_inr, value_inr: plan.goal_progress?.value_inr,
    pct: plan.goal_progress?.pct, source: plan.goal_progress?.source,
  } : null);
  if (!g) {
    return (
      <Card>
        <Label>Your goal</Label>
        <p className="text-[15px]">Set a goal in rupees and get a simple monthly plan, with ₹1,00,000 of practice money to try it.</p>
        <LinkButton to="/app/plan" className="w-full mt-3">Make my plan</LinkButton>
      </Card>
    );
  }
  const p = Math.max(0, Math.min(100, Number(g.pct) || 0));
  return (
    <Card data-testid="goal-card">
      <Label>Your goal</Label>
      <p className="font-bzserif text-[22px] font-semibold leading-tight">{g.name || "My goal"}</p>
      <div className="flex items-baseline justify-between mt-3 text-[14px]">
        <span><b className="text-[18px] tabular">{inr(g.value_inr || 0)}</b> <span className="text-bz-muted">of {inr(g.target_inr)}</span></span>
        <span className="font-semibold tabular">{p.toFixed(0)}%</span>
      </div>
      <Meter value={p} className="mt-2" label="Goal progress" />
      <p className="text-[12px] text-bz-muted mt-2">
        {g.source === "portfolio" ? "From your linked exchange." : g.source === "paper" ? "Practice only: this is your Paper Money, not real money. Link an exchange to track the real thing." : "Start Paper Money or link an exchange to track it."}
      </p>
      <Link to="/app/plan" className="inline-block mt-2 text-sm font-semibold text-bz-accent">Open my plan</Link>
    </Card>
  );
}

function VerdictChanges() {
  const q = useQuery({ queryKey: ["verdicts-today"], queryFn: async () => (await api.get("/verdicts/today")).data });
  if (q.isLoading) return <Card><Skeleton lines={3} /></Card>;
  if (q.isError) return null;
  const changed = (q.data?.coins || []).filter((c) => c.changed_from);
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <Label className="mb-0">Verdict changes today</Label>
        <Link to="/app/verdicts" className="text-sm font-semibold text-bz-accent">All verdicts</Link>
      </div>
      {changed.length === 0 ? (
        <p className="text-[15px] text-bz-muted mt-3">No coin changed its verdict today.</p>
      ) : (
        <ul className="mt-2 divide-y divide-bz-line">
          {changed.map((c) => (
            <li key={c.symbol}>
              <Link to={`/app/coin/${c.symbol}`} className="flex items-center justify-between gap-3 py-3 min-h-[52px]">
                <span className="min-w-0"><span className="block font-semibold">{c.name || c.symbol} <span className="text-bz-muted font-normal text-[13px]">{c.symbol}</span></span>
                  <span className="block text-[13px] text-bz-muted">was {c.changed_from}</span></span>
                <VerdictChip v={c.verdict} conf={c.confidence} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function RadarPeek() {
  const q = useQuery({ queryKey: ["radar"], queryFn: async () => (await api.get("/radar", { _silentGate: true })).data });
  const items = (q.data?.items || []).slice(0, 3);
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <Label className="mb-0">Early Coin Radar</Label>
        <Link to="/app/radar" className="text-sm font-semibold text-bz-accent">See all</Link>
      </div>
      {q.isLoading ? <Skeleton lines={2} className="mt-3" /> : items.length === 0 ? (
        <p className="text-[15px] text-bz-muted mt-3">Nothing new on the radar yet.</p>
      ) : (
        <ul className="mt-2 divide-y divide-bz-line">
          {items.map((r) => (
            <li key={r.id || r.symbol} className="py-2.5 flex items-center justify-between gap-3">
              <span className="min-w-0"><span className="block font-semibold truncate">{r.name || r.symbol} <span className="text-[13px] text-bz-muted font-normal">{r.symbol}</span></span>
                <span className="block text-[12px] text-bz-muted">{r.kind === "new_listing" ? "New listing" : "Trending"}{r.venue ? ` · ${venueName(r.venue)}` : ""}</span></span>
              <span className="flex flex-col items-end gap-1"><Move v={r.change_24h} className="text-[13px]" />{r.xray && <XrayChip label={r.xray.label} />}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Tiles() {
  const { user, plan } = useAuth();
  const admin = user?.role === "admin";
  const items = [...NAV_MAIN.slice(1), ...NAV_PRO];
  return (
    <div>
      <Label>Your tools</Label>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {items.map(({ to, key, label, sub, icon: Icon, feature }) => {
          const locked = feature && !admin && !plan?.features?.[feature];
          return (
            <Link key={to} to={to} data-testid={`tile-${key}`}
              className="rounded-bzcard border border-bz-line bg-bz-card p-3.5 min-h-[104px] flex flex-col hover:border-bz-line-strong">
              <span className="flex items-center justify-between"><Icon className="w-5 h-5 text-bz-gold" strokeWidth={1.75} aria-hidden />{locked && <Lock className="w-3.5 h-3.5 text-bz-muted" aria-label="Locked" />}</span>
              <span className="mt-2 text-[14.5px] font-semibold leading-tight">{label}</span>
              <span className="text-[12px] text-bz-muted mt-0.5 leading-snug">{sub}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export default function Today() {
  const { user } = useAuth();
  const canAsk = useFeature("ask");
  const canRadar = useFeature("radar");
  const coach = useQuery({ queryKey: ["coach"], queryFn: async () => (await api.get("/ask/coach", { _silentGate: true })).data, enabled: canAsk });
  const plans = useQuery({ queryKey: ["plans"], queryFn: async () => (await api.get("/plan", { _silentGate: true })).data });
  const inbox = useQuery({ queryKey: ["inbox"], queryFn: async () => (await api.get("/inbox")).data, staleTime: 60_000 });
  const first = (plans.data?.plans || [])[0];
  const unread = inbox.data?.unread || 0;
  const firstName = (user?.name || "").split(" ")[0];
  return (
    <div className="space-y-5">
      <header>
        <div className="flex items-center gap-3">
          <span className="w-2.5 h-2.5 rounded-[3px] bg-bz-gold" aria-hidden />
          <span className="font-bzmono text-[11px] tracking-[0.28em] uppercase"><span className="text-bz-gold-deep">Today</span><span className="text-bz-muted">_{sdate(istToday())}</span></span>
        </div>
        <h1 className="font-bzserif mt-4 text-[30px] sm:text-[40px] font-semibold leading-[1.08]">
          {greeting()}{firstName ? "," : ""} <span className="text-bz-accent">{firstName || "there"}.</span>
        </h1>
      </header>

      <CrashBanner crash={coach.data?.crash} />

      {unread > 0 && (
        <Link to="/app/inbox" className="flex items-center gap-3 rounded-bzcard border border-bz-gold bg-bz-gold-tint px-4 py-3 min-h-[52px]" data-testid="today-inbox">
          <Bell className="w-5 h-5 text-bz-gold-deep" aria-hidden />
          <span className="font-semibold">{unread} new alert{unread === 1 ? "" : "s"} in your inbox</span>
        </Link>
      )}

      <PulseStrip />

      <div className="grid gap-4 md:grid-cols-2 items-start">
        {plans.isLoading && !coach.data ? <Card><Skeleton lines={3} /></Card> : <GoalCard goal={coach.data?.goal} plan={first} />}
        <VerdictChanges />
      </div>

      {canRadar && <RadarPeek />}
      {!canRadar && (
        <Card inset className="flex items-center justify-between gap-3">
          <span className="text-[14.5px]"><b>Early Coin Radar</b>, News Decoder, Baskets and more come with the ₹5,000 plan.</span>
          <Chip tone="gold">₹5,000</Chip>
        </Card>
      )}

      <Tiles />
    </div>
  );
}
