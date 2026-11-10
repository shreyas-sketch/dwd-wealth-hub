// Domain pieces shared across screens: verdict chip, moves, lock card, usage line, X-Ray label, coin logo.
import { Link } from "react-router-dom";
import { Lock, Star } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth, useFeature } from "@/context/AuthContext";
import { featureInfo, PLAN_LABEL } from "@/lib/features";
import { pct } from "@/lib/format";
import { track } from "@/lib/attribution";
import { Card, Chip, LinkButton } from "./ui";

export const VERDICT_TONE = { Bullish: "bull", Bearish: "bear", Neutral: "gold" };
export const VERDICT_TEXT = { Bullish: "text-bz-accent", Bearish: "text-bz-miss", Neutral: "text-bz-gold-deep" };

export function VerdictChip({ v, conf }) {
  if (!v) return <Chip>No verdict</Chip>;
  return <Chip tone={VERDICT_TONE[v] || "muted"}>{v}{conf != null ? ` · ${conf}%` : ""}</Chip>;
}

export function Move({ v, className = "", decimals = 1 }) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return <span className={`text-bz-muted ${className}`}>—</span>;
  const n = Number(v);
  return <span className={`${n > 0 ? "text-bz-accent" : n < 0 ? "text-bz-miss" : "text-bz-muted"} font-semibold tabular ${className}`}>{pct(n, decimals)}</span>;
}

// X-Ray label: safe / risky / likely_scam.
export const XRAY = {
  safe: { label: "Looks safe", tone: "bull", bar: "accent" },
  risky: { label: "Risky", tone: "gold", bar: "gold" },
  likely_scam: { label: "Likely scam", tone: "bear", bar: "miss" },
  unchecked: { label: "Not checked yet", tone: "muted", bar: "gold" },   // the check couldn't run; retried later
};
export function XrayChip({ label, score }) {
  const x = XRAY[label];
  if (!x) return null;
  return <Chip tone={x.tone}>X-Ray: {x.label}{score != null ? ` · ${score}` : ""}</Chip>;
}

// Simple round coin badge with the symbol's first letters (no third-party logos).
export function CoinBadge({ symbol, size = 36 }) {
  const s = String(symbol || "?").toUpperCase();
  return (
    <span className="inline-grid place-items-center rounded-full bg-bz-gold-tint text-bz-gold-deep font-bzdisplay font-bold shrink-0"
      style={{ width: size, height: size, fontSize: size * 0.3 }} aria-hidden>
      {s.slice(0, s.length > 4 ? 3 : 4)}
    </span>
  );
}

// "You've used 2 of 30 this month" from {used, limit}.
// `what` is the plural noun ("checks", "chart reads"); one use reads "1 check" (QA 10 Nov: "1 checks used").
export function UsageLine({ usage, what = "checks", className = "" }) {
  if (!usage || usage.used == null) return null;
  const n = Number(usage.used);
  const noun = n === 1 ? what.replace(/s$/, "") : what;
  const text = usage.limit == null
    ? `${n.toLocaleString("en-IN")} ${noun} used this month. Unlimited on your plan.`
    : `You've used ${n.toLocaleString("en-IN")} of ${usage.limit} ${what} this month.`;
  return <p className={`text-[13px] text-bz-muted ${className}`}>{text}</p>;
}

export function planNeededLabel(p) {
  return p === "pro" ? "₹5,000 plan" : "₹2,000 plan";
}

// Shown on a locked page or after a 403/402 from the API.
//   kind "locked": what the feature does + "Included in the ₹2,000 plan" + Upgrade
//   kind "limit":  "You've used N of M this month" + Upgrade
export function LockCard({ feature, planNeeded, kind = "locked", used, limit, msg, onAction }) {
  const { user } = useAuth();
  const info = featureInfo(feature);
  const need = planNeeded || info.plan || "lite";
  const isLimit = kind === "limit";
  return (
    <Card className="border-bz-gold" data-testid={isLimit ? "limit-card" : "lock-card"}>
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-full bg-bz-gold-tint text-bz-gold-deep grid place-items-center shrink-0"><Lock className="w-5 h-5" aria-hidden /></span>
        <div className="min-w-0">
          <p className="font-bzdisplay text-[22px] font-bold leading-tight">{info.name}</p>
          {isLimit ? (
            <p className="text-[15px] mt-1.5">
              {used != null && limit != null ? `You've used ${used} of ${limit} this month.` : msg || "You've reached this month's limit."}
              {" "}More with the {planNeededLabel(need)}.
            </p>
          ) : (
            <>
              <p className="text-[15px] mt-1.5 text-bz-muted">{info.what}</p>
              <p className="text-[15px] mt-2 font-semibold">Included in the {planNeededLabel(need)}.</p>
            </>
          )}
        </div>
      </div>
      {user ? (
        <LinkButton to={`/app/plans?plan=${need}&from=${feature || "gate"}`} className="w-full mt-4" data-testid="lock-upgrade"
          onClick={() => { track("upgrade_viewed", { feature, plan: need, kind }); onAction?.(); }}>
          Upgrade to the {planNeededLabel(need)}
        </LinkButton>
      ) : (
        <LinkButton to={`/login?next=${encodeURIComponent(window.location.pathname)}`} className="w-full mt-4" onClick={onAction}>
          Create your account
        </LinkButton>
      )}
    </Card>
  );
}

// Wrap a page: show LockCard when PlanInfo.features[feature] is false.
export function Gate({ feature, children, header = null }) {
  const ok = useFeature(feature);
  if (ok) return children;
  return (
    <div className="space-y-4">
      {header}
      <LockCard feature={feature} />
    </div>
  );
}

export function PlanChip({ plan }) {
  if (!plan) return null;
  const tone = plan.plan === "pro" ? "solid" : plan.plan === "lite" ? "gold" : "muted";
  return <Chip tone={tone}>{plan.label || PLAN_LABEL[plan.plan] || "Free"}{plan.source === "trial" ? " · trial" : ""}</Chip>;
}

// ---- Watchlist ---------------------------------------------------------------
export function useWatchlist() {
  const can = useFeature("watchlist");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["watchlist"], queryFn: async () => (await api.get("/watchlist", { _silentGate: true })).data, enabled: can });
  const symbols = new Set((q.data?.symbols || []).map((s) => String(s).toUpperCase()));
  const m = useMutation({
    mutationFn: async ({ symbol, on }) => (on ? api.post(`/watchlist/${symbol}`) : api.delete(`/watchlist/${symbol}`)).then((r) => r.data),
    onSuccess: (data) => {
      if (data?.symbols) qc.setQueryData(["watchlist"], data);
      qc.invalidateQueries({ queryKey: ["verdicts-today"] });
    },
  });
  return { can, loaded: !!q.data, has: (s) => symbols.has(String(s).toUpperCase()), toggle: (s, on) => m.mutate({ symbol: s, on }), busy: m.isPending };
}

export function WatchStar({ symbol, watched, wl }) {
  const on = wl.loaded ? wl.has(symbol) : !!watched;
  return (
    <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); wl.toggle(symbol, !on); }}
      aria-pressed={on} aria-label={on ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`}
      data-testid={`watch-${symbol}`}
      className="w-11 h-11 grid place-items-center rounded-full hover:bg-bz-inset shrink-0" title={wl.can ? "Watchlist" : "Watchlist is in the ₹2,000 plan"}>
      <Star className={`w-5 h-5 ${on ? "fill-bz-gold text-bz-gold" : "text-bz-muted"}`} strokeWidth={1.75} aria-hidden />
    </button>
  );
}

export function BackLink({ to, children }) {
  return (
    <Link to={to} className="inline-flex items-center gap-1.5 text-[15px] font-semibold text-bz-muted hover:text-bz-ink min-h-[40px]">
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M15 6l-6 6 6 6" /></svg>
      {children}
    </Link>
  );
}
