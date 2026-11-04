// "My real portfolio": holdings from linked exchanges and how they compare to the plan.
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Link2 } from "lucide-react";
import { api } from "@/lib/api";
import { ago, inr, usd, venueName } from "@/lib/format";
import { Card, Empty, ErrorCard, Label, LinkButton, Skeleton } from "../ui";

export default function PortfolioSection() {
  const q = useQuery({ queryKey: ["portfolio"], queryFn: async () => (await api.get("/portfolio", { _silentGate: true })).data });
  if (q.isLoading) return <Card><Skeleton lines={3} /></Card>;
  if (q.isError) return <ErrorCard error={q.error} onRetry={() => q.refetch()} what="your portfolio" />;
  const d = q.data || {};
  if (!(d.linked || []).length) {
    return (
      <Empty icon={Link2} title="No exchange linked yet"
        sub="Link your KuCoin or Binance account (trade-only key, no withdrawals) to see your real coins next to your plan."
        action={<LinkButton to="/app/autopilot" variant="secondary">Link an exchange in Autopilot</LinkButton>} />
    );
  }
  const holdings = d.holdings || [];
  const vs = d.vs_plan || [];
  return (
    <div className="space-y-3" data-testid="portfolio-section">
      <Card>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <Label className="mb-1">Real portfolio</Label>
            <div className="font-bzserif text-[32px] font-semibold leading-none tabular">{inr(d.total_inr)}</div>
            <div className="text-[13px] text-bz-muted mt-1">{usd(d.total_usd)} · {(d.linked || []).map(venueName).join(" + ")}{d.as_of ? ` · ${ago(d.as_of)}` : ""}</div>
          </div>
          <Link to="/app/autopilot" className="text-sm font-semibold text-bz-accent">Manage exchanges</Link>
        </div>
        {holdings.length > 0 ? (
          <ul className="mt-4 divide-y divide-bz-line">
            {holdings.map((h, i) => (
              <li key={`${h.venue}-${h.symbol}-${i}`} className="py-2.5 flex items-center justify-between gap-3 text-[14px]">
                <span className="min-w-0"><b>{h.symbol}</b> <span className="text-bz-muted">· {venueName(h.venue)} · {Number(h.qty || 0).toLocaleString("en-IN", { maximumFractionDigits: 6 })}</span></span>
                <span className="tabular font-semibold">{inr(h.value_inr)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-[14px] text-bz-muted mt-3">No coins on your linked exchange yet.</p>}
      </Card>
      {vs.length > 0 && (
        <Card>
          <Label>You vs your plan</Label>
          <ul className="space-y-3">
            {vs.map((r) => (
              <li key={r.symbol}>
                <div className="flex justify-between text-[14px]"><b>{r.symbol}</b><span className="text-bz-muted tabular">plan {Number(r.plan_pct || 0)}% · you {Number(r.actual_pct || 0).toFixed(0)}%</span></div>
                <div className="relative h-2.5 mt-1 rounded-full bg-bz-inset overflow-hidden">
                  <div className="absolute inset-y-0 left-0 bg-bz-gold rounded-full" style={{ width: `${Math.min(100, Number(r.actual_pct) || 0)}%` }} />
                  <div className="absolute inset-y-[-2px] w-[3px] bg-bz-ink" style={{ left: `calc(${Math.min(100, Number(r.plan_pct) || 0)}% - 1px)` }} aria-hidden />
                </div>
              </li>
            ))}
          </ul>
          <p className="text-[12px] text-bz-muted mt-2">Orange bar: what you hold. Dark line: what the plan suggests.</p>
        </Card>
      )}
    </div>
  );
}
