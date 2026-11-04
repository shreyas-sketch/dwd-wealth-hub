// A crypto plan: allocation bar, bad / average / good scenarios (labelled assumptions), yearly table, goal progress.
import { CheckCircle2, XCircle } from "lucide-react";
import { inr, inrShort, pct } from "@/lib/format";

// Full rupees on wider screens, "₹19.7 L" on a phone so all five columns fit without sideways scrolling.
const Rs = ({ v }) => <><span className="sm:hidden">{inrShort(v)}</span><span className="hidden sm:inline">{inr(v)}</span></>;
import { Card, Chip, Label, Meter } from "../ui";
import WeightBar from "../WeightBar";

const SCEN = {
  bad: { title: "Bad years", cls: "border-bz-miss", tone: "text-bz-miss" },
  average: { title: "Average", cls: "border-bz-line-strong", tone: "text-bz-ink" },
  good: { title: "Good years", cls: "border-bz-accent", tone: "text-bz-accent" },
};
const RISK_LABEL = { safe: "Safe", moderate: "Moderate", aggressive: "Aggressive" };

export default function PlanCard({ p, actions = null }) {
  const gp = p.goal_progress || {};
  const gpPct = Math.max(0, Math.min(100, Number(gp.pct) || 0));
  return (
    <div className="space-y-4" data-testid="plan-card">
      <Card>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <Label className="mb-1">Goal</Label>
            <h2 className="font-bzserif text-[26px] font-semibold leading-tight">{p.goal_name || "My goal"}</h2>
            <p className="text-[14.5px] text-bz-muted mt-1">
              {inr(p.target_inr)} in {p.years} year{p.years === 1 ? "" : "s"} · {p.lump_sum_inr ? `${inr(p.lump_sum_inr)} now + ` : ""}{inr(p.monthly_inr)} a month
            </p>
          </div>
          <Chip tone="gold">{RISK_LABEL[p.risk] || p.risk}</Chip>
        </div>
        {p.invested_total_inr != null && <p className="text-[14px] mt-3">You will put in <b className="tabular">{inr(p.invested_total_inr)}</b> in total.</p>}
        {(p.allocation || []).length > 0 && (
          <div className="mt-4">
            <Label className="mb-2">How the money is split</Label>
            <WeightBar items={p.allocation} />
          </div>
        )}
        {gp.source && gp.source !== "none" && (
          <div className="mt-5 pt-4 border-t border-bz-line">
            <div className="flex items-baseline justify-between text-[14px]">
              <span>Progress: <b className="tabular">{inr(gp.value_inr)}</b> <span className="text-bz-muted">({gp.source === "portfolio" ? "real portfolio" : "practice only — paper money, not real"})</span></span>
              <span className="font-semibold tabular">{gpPct.toFixed(0)}%</span>
            </div>
            <Meter value={gpPct} className="mt-2" label="Goal progress" />
          </div>
        )}
        {actions && <div className="mt-4 flex flex-wrap gap-2">{actions}</div>}
      </Card>

      {(p.scenarios || []).length > 0 && (
        <div>
          <Label>Where it could end up</Label>
          <div className="grid gap-2 sm:grid-cols-3">
            {p.scenarios.map((s) => {
              const m = SCEN[s.key] || SCEN.average;
              return (
                <div key={s.key} className={`rounded-bzcard border-2 ${m.cls} bg-bz-card p-4`} data-testid={`scenario-${s.key}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{s.label || m.title}</span>
                    <Chip>Assumption</Chip>
                  </div>
                  <div className={`text-[24px] font-semibold tabular mt-2 ${m.tone}`}>{inr(s.end_value_inr)}</div>
                  <div className="text-[13px] text-bz-muted">if it grows {pct(s.annual_pct, 0, false)} a year</div>
                  <div className={`mt-2 flex items-center gap-1.5 text-[13.5px] font-semibold ${s.reaches_goal ? "text-bz-accent" : "text-bz-miss"}`}>
                    {s.reaches_goal ? <CheckCircle2 className="w-4 h-4" aria-hidden /> : <XCircle className="w-4 h-4" aria-hidden />}
                    {s.reaches_goal ? "Reaches the goal" : "Falls short of the goal"}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-[12px] text-bz-muted mt-2">These growth rates are assumptions to help you plan, not predictions. Crypto can also fall.</p>
        </div>
      )}

      {(p.yearly || []).length > 0 && (
        <Card>
          <Label>Year by year</Label>
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full text-[13px] sm:text-[14px] tabular sm:min-w-[440px]">
              <thead>
                <tr className="text-left text-bz-muted font-bzmono text-[10.5px] uppercase tracking-[0.12em]">
                  <th className="py-2 pr-2 font-medium">Year</th><th className="py-2 px-2 font-medium text-right">Put in</th>
                  <th className="py-2 px-2 font-medium text-right">Bad</th><th className="py-2 px-2 font-medium text-right">Average</th><th className="py-2 pl-2 font-medium text-right">Good</th>
                </tr>
              </thead>
              <tbody>
                {p.yearly.map((y) => (
                  <tr key={y.year} className="border-t border-bz-line">
                    <td className="py-2 pr-2">{y.year}</td>
                    <td className="py-2 px-2 text-right"><Rs v={y.invested_inr} /></td>
                    <td className="py-2 px-2 text-right text-bz-miss"><Rs v={y.bad_inr} /></td>
                    <td className="py-2 px-2 text-right"><Rs v={y.average_inr} /></td>
                    <td className="py-2 pl-2 text-right text-bz-accent"><Rs v={y.good_inr} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {p.note && <p className="text-[12px] text-bz-muted">{p.note}</p>}
    </div>
  );
}
