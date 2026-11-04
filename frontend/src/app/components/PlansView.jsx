// Pricing cards from GET /plans/catalog. Used on /plans (public) and /app/plans (inside the shell).
import { useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useCheckout } from "@/lib/checkout";
import { track } from "@/lib/attribution";
import { hdate, inr } from "@/lib/format";
import { PLAN_LABEL } from "@/lib/features";
import { Button, Card, Chip, ErrorCard, OkLine, SkeletonCard } from "./ui";

const RANK = { free: 0, lite: 1, pro: 2 };

export function usePlansCatalog() {
  return useQuery({ queryKey: ["plans-catalog"], queryFn: async () => (await api.get("/plans/catalog")).data, staleTime: 10 * 60_000 });
}

export function PlanCard({ p, current, highlight, onBuy, busy, compact = false }) {
  const isCur = current === p.id;
  const lower = current && RANK[p.id] < RANK[current];
  return (
    <Card className={`flex flex-col ${highlight ? "border-bz-gold border-2" : ""}`} data-testid={`plan-${p.id}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-bzdisplay text-[22px] font-bold leading-tight">{p.name || PLAN_LABEL[p.id]}</h3>
          <div className="mt-1.5">
            <span className="font-bzdisplay text-[31px] font-bold tabular">{inr(p.price_inr || 0, 0)}</span>
            <span className="text-bz-muted text-[14px]">{p.price_inr ? " + GST" : ""} / {p.period || "month"}</span>
            {p.total_inr ? <div className="text-[12.5px] text-bz-muted tabular">{inr(p.total_inr, 0)} a month incl. {p.gst_pct || 18}% GST</div> : null}
          </div>
        </div>
        {isCur ? <Chip tone="bull">Your plan</Chip> : p.id === "pro" ? <Chip tone="gold">Everything</Chip> : null}
      </div>
      {!compact && (
        <ul className="mt-3 space-y-2 text-[14.5px] flex-1">
          {(p.features || []).map((f) => <li key={f} className="flex gap-2"><Check className="w-4 h-4 text-bz-accent shrink-0 mt-1" aria-hidden />{f}</li>)}
        </ul>
      )}
      {onBuy && p.id !== "free" && !isCur && !lower && (
        <Button className="w-full mt-4" loading={busy === p.id} onClick={() => onBuy(p.id)} data-testid={`upgrade-${p.id}`}>
          Upgrade to {p.name || PLAN_LABEL[p.id]}
        </Button>
      )}
    </Card>
  );
}

export default function PlansView({ inShell = false }) {
  const { user, plan } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const cat = usePlansCatalog();
  const { buy, busy, error, done } = useCheckout();
  const want = params.get("plan");

  useEffect(() => { track("upgrade_viewed", { from: params.get("from") || (inShell ? "app" : "public"), plan: want }); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onBuy = (id) => {
    if (!user) { nav(`/login?next=${encodeURIComponent(`/app/plans?plan=${id}`)}`); return; }
    buy(id);
  };

  if (cat.isLoading) return <div className="grid gap-3 md:grid-cols-3"><SkeletonCard lines={5} /><SkeletonCard lines={5} /><SkeletonCard lines={5} /></div>;
  if (cat.isError) return <ErrorCard error={cat.error} onRetry={() => cat.refetch()} what="the plans" />;
  const plans = cat.data?.plans || [];
  const current = user ? (plan?.source === "trial" ? null : plan?.plan || "free") : null;
  return (
    <div className="space-y-4">
      {cat.data?.trial_days ? (
        <Card inset><p className="text-[15px]"><b>New accounts get {cat.data.trial_days} days of the ₹5,000 plan free.</b> No card needed. After that you stay on Free unless you upgrade.</p></Card>
      ) : null}
      {user && plan?.source === "trial" && (
        <p className="text-[14px] text-bz-muted">You're on a free trial of the {plan.label || "₹5,000 plan"}{plan.trial_ends_at ? ` until ${hdate(plan.trial_ends_at)}` : ""}. Pick a plan to keep your features.</p>
      )}
      {done && (
        <Card className="border-bz-accent" role="status">
          <OkLine>Payment received. You're now on the {done.label || PLAN_LABEL[done.plan] || "new plan"}{done.paid_until ? ` until ${hdate(done.paid_until)}` : ""}.</OkLine>
          <Link to="/app" className="text-sm font-semibold text-bz-accent">Back to the app</Link>
        </Card>
      )}
      {plans.length === 0 ? (
        <Card inset><p className="text-[15px]">Plans will show here shortly.</p></Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-3">
          {plans.map((p) => <PlanCard key={p.id} p={p} current={current} highlight={want ? want === p.id : p.id === "lite"} onBuy={onBuy} busy={busy} />)}
        </div>
      )}
      {error && <p className="text-sm text-bz-miss" role="alert">{error}</p>}
      <p className="text-[12px] text-bz-muted">Monthly plans renew automatically by Razorpay. Cancel any time from Account; your plan runs to the end of the month you paid for.</p>
    </div>
  );
}
