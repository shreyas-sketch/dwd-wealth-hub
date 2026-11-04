// Admin › Pulse: KPI tiles, signups by day, by source, plan mix, feature usage (7 days).
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { inr, sdate } from "@/lib/format";
import { PLAN_LABEL } from "@/lib/features";
import { AXIS_TICK, C, TOOLTIP } from "../components/chart";
import { Card, Label } from "../components/ui";
import { AdminLoadable, Kpi, useAdmin } from "./shared";

function Bars({ rows, labelKey, valueKey = "count", label }) {
  const list = rows || [];
  const max = Math.max(1, ...list.map((r) => Number(r[valueKey]) || 0));
  if (!list.length) return <p className="text-sm text-bz-muted">No data yet.</p>;
  return (
    <ul className="space-y-2" aria-label={label}>
      {list.map((r) => (
        <li key={r[labelKey]}>
          <div className="flex justify-between text-[13.5px]"><span className="truncate pr-2">{r.__label || r[labelKey] || "—"}</span><span className="tabular font-semibold">{Number(r[valueKey] || 0).toLocaleString("en-IN")}</span></div>
          <div className="h-2 rounded-full bg-bz-inset mt-1 overflow-hidden"><div className="h-full bg-bz-gold rounded-full" style={{ width: `${((Number(r[valueKey]) || 0) / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

export default function Pulse() {
  const q = useAdmin("pulse");
  return (
    <AdminLoadable q={q} what="the pulse">
      {(d) => {
        const k = d.kpis || {};
        return (
          <div className="space-y-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Kpi label="Users" value={Number(k.users_total ?? 0).toLocaleString("en-IN")} />
              <Kpi label="Signups today" value={k.signups_today} sub={`${k.signups_7d ?? 0} in 7 days`} />
              <Kpi label="On trial" value={k.trial_active} />
              <Kpi label="MRR (before GST)" value={inr(k.mrr_inr)} tone="gold" />
              <Kpi label="₹2,000 active" value={k.lite_active} />
              <Kpi label="₹5,000 active" value={k.pro_active} />
              <Kpi label="Paid conversion" value={k.paid_conversion_pct != null ? `${k.paid_conversion_pct}%` : "—"} tone="up" />
              <Kpi label="Signups 7d" value={k.signups_7d} />
            </div>
            <Card>
              <Label>Signups by day</Label>
              {(d.signups_by_day || []).length ? (
                <div className="h-60 -mx-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.signups_by_day} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke={C.line} vertical={false} />
                      <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={sdate} minTickGap={20} />
                      <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={36} allowDecimals={false} />
                      <Tooltip {...TOOLTIP} cursor={{ fill: "var(--bz-inset)" }} labelFormatter={sdate} formatter={(v) => [v, "Signups"]} />
                      <Bar dataKey="count" fill={C.gold} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : <p className="text-sm text-bz-muted">No signups yet.</p>}
            </Card>
            <div className="grid gap-4 md:grid-cols-3">
              <Card><Label>By source</Label><Bars rows={d.by_source} labelKey="source" label="Signups by source" /></Card>
              <Card><Label>Plan mix</Label><Bars rows={(d.plan_mix || []).map((r) => ({ ...r, __label: PLAN_LABEL[r.plan] || r.plan }))} labelKey="plan" label="Plan mix" /></Card>
              <Card><Label>Feature usage · 7 days</Label><Bars rows={d.feature_usage_7d} labelKey="feature" label="Feature usage" /></Card>
            </div>
          </div>
        );
      }}
    </AdminLoadable>
  );
}
