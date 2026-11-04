// Create / edit a crypto plan: goal name, target ₹, lump sum ₹, monthly ₹, years, risk.
import { useState } from "react";
import { Button, Field, Input, MoneyInput, Segmented } from "../ui";

export const RISKS = [
  { value: "safe", label: "Safe" },
  { value: "moderate", label: "Moderate" },
  { value: "aggressive", label: "Aggressive" },
];
const RISK_NOTE = {
  safe: "Mostly Bitcoin, some Ethereum and a cash buffer.",
  moderate: "Bitcoin and Ethereum, with a little Solana and XRP.",
  aggressive: "More Solana and XRP. Bigger swings both ways.",
};
const EMPTY = { goal_name: "", target_inr: 1000000, lump_sum_inr: 0, monthly_inr: 5000, years: 5, risk: "moderate" };

export default function PlanForm({ initial, onSubmit, onCancel, busy, error }) {
  const [f, setF] = useState(() => ({ ...EMPTY, ...(initial ? {
    goal_name: initial.goal_name || "", target_inr: initial.target_inr ?? EMPTY.target_inr, lump_sum_inr: initial.lump_sum_inr ?? 0,
    monthly_inr: initial.monthly_inr ?? EMPTY.monthly_inr, years: initial.years ?? 5, risk: initial.risk || "moderate",
  } : {}) }));
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const valid = f.goal_name.trim() && Number(f.target_inr) > 0 && (Number(f.monthly_inr) > 0 || Number(f.lump_sum_inr) > 0) && Number(f.years) > 0;
  const submit = (e) => {
    e.preventDefault();
    if (!valid) return;
    onSubmit({
      goal_name: f.goal_name.trim(), target_inr: Number(f.target_inr) || 0, lump_sum_inr: Number(f.lump_sum_inr) || 0,
      monthly_inr: Number(f.monthly_inr) || 0, years: Number(f.years), risk: f.risk,
    });
  };
  return (
    <form onSubmit={submit} className="space-y-4" data-testid="plan-form">
      <Field label="What is the goal for?">
        <Input value={f.goal_name} onChange={(e) => set("goal_name")(e.target.value)} placeholder="e.g. Daughter's college, Retirement top-up" maxLength={80} data-testid="plan-goal" />
      </Field>
      <Field label="Target amount" hint="How much you want to have at the end.">
        <MoneyInput value={f.target_inr} onChange={set("target_inr")} data-testid="plan-target" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="One-time amount now"><MoneyInput value={f.lump_sum_inr} onChange={set("lump_sum_inr")} data-testid="plan-lump" /></Field>
        <Field label="Every month"><MoneyInput value={f.monthly_inr} onChange={set("monthly_inr")} data-testid="plan-monthly" /></Field>
      </div>
      <Field label="For how many years">
        <Segmented options={[1, 3, 5, 7, 10].map((y) => ({ value: y, label: `${y}y` }))} value={Number(f.years)} onChange={set("years")} label="Years" testid="plan-years" />
      </Field>
      <Field label="How much risk can you take?" hint={RISK_NOTE[f.risk]}>
        <Segmented options={RISKS} value={f.risk} onChange={set("risk")} label="Risk" testid="plan-risk" />
      </Field>
      {error && <p className="text-sm text-bz-miss" role="alert">{error}</p>}
      <div className="flex flex-col sm:flex-row gap-2">
        <Button type="submit" className="flex-1" loading={busy} disabled={!valid} data-testid="plan-save">{initial ? "Save changes" : "Make my plan"}</Button>
        {onCancel && <Button variant="secondary" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}
