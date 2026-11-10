// Admin › Settings: trial days, scenario rates (% a year), crash levels, anonymous X-Ray per day.
//
// Limits come from GET /admin/settings/spec, the same table the server validates against, so the form never
// accepts a value the server would refuse, and the server never silently clips one (QA 3 Nov).
// Errors are shown per field; the server's {errors: {field: msg}} lands on the same fields.
import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Button, Card, Field, Input, Label, OkLine } from "../components/ui";
import { AdminLoadable, useAdmin } from "./shared";

// Fallback when the spec request fails: same numbers as backend/appsettings.py SPEC.
const FALLBACK_SPEC = {
  fields: {
    trial_days: { label: "Trial days", min: 0, max: 30, integer: true, unit: "days" },
    anon_xray_per_day: { label: "X-Ray checks a day without login", min: 0, max: 20, integer: true, unit: "" },
    "scenario_rates.bad": { label: "Bad-case rate", min: -50, max: 100, integer: false, unit: "%" },
    "scenario_rates.average": { label: "Average-case rate", min: -50, max: 100, integer: false, unit: "%" },
    "scenario_rates.good": { label: "Good-case rate", min: -50, max: 100, integer: false, unit: "%" },
    crash_levels: { label: "Crash level", min: 5, max: 90, integer: true, unit: "%" },
  },
  max_crash_levels: 6,
};

// Form keys → spec / server field names.
const KEY = { trial_days: "trial_days", anon: "anon_xray_per_day", bad: "scenario_rates.bad", average: "scenario_rates.average",
  good: "scenario_rates.good", crash: "crash_levels" };

const fmt = (n) => (Number.isInteger(n) ? String(n) : String(n));
const unitOf = (r) => (r.unit && r.unit !== "%" ? ` ${r.unit}` : r.unit || "");

function checkNumber(raw, rule) {
  if (raw === "" || raw == null) return `${rule.label} is required.`;
  const v = Number(raw);
  if (!Number.isFinite(v)) return `${rule.label} must be a number.`;
  if (rule.integer && !Number.isInteger(v)) return `${rule.label} must be a whole number.`;
  if (v < rule.min || v > rule.max) return `${rule.label} must be between ${fmt(rule.min)}${unitOf(rule)} and ${fmt(rule.max)}${unitOf(rule)} (you entered ${fmt(v)}).`;
  return "";
}

export function validateSettings(f, spec) {
  const F = spec.fields;
  const errors = {};
  for (const k of ["trial_days", "anon", "bad", "average", "good"]) {
    const e = checkNumber(f[k], F[KEY[k]]);
    if (e) errors[k] = e;
  }
  if (!errors.bad && !errors.average && !errors.good && !(Number(f.bad) <= Number(f.average) && Number(f.average) <= Number(f.good))) {
    errors.rates = "Rates must go up from bad to average to good.";
  }
  const parts = String(f.crash).split(",").map((x) => x.trim()).filter(Boolean);
  if (!parts.length) errors.crash = "Add at least one crash level, e.g. 20, 30, 40.";
  else if (parts.length > spec.max_crash_levels) errors.crash = `Use at most ${spec.max_crash_levels} crash levels.`;
  else {
    const bad = parts.map((p) => checkNumber(p, F.crash_levels)).find(Boolean);
    if (bad) errors.crash = bad;
    else if (new Set(parts.map(Number)).size !== parts.length) errors.crash = "Each crash level can appear only once.";
  }
  return errors;
}

// Server field name → form key.
const fromServer = (field) => {
  if (field === "scenario_rates") return "rates";
  const hit = Object.entries(KEY).find(([, v]) => v === field);
  return hit ? hit[0] : "form";
};

function Editor({ s, spec }) {
  const qc = useQueryClient();
  const F = spec.fields;
  const [f, setF] = useState({
    trial_days: s.trial_days ?? 3,
    bad: s.scenario_rates?.bad ?? -15, average: s.scenario_rates?.average ?? 15, good: s.scenario_rates?.good ?? 35,
    crash: (s.crash_levels || [20, 30, 40]).join(", "),
    anon: s.anon_xray_per_day ?? 1,
  });
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  const [ok, setOk] = useState("");
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setErrors(({ [k]: _, form: __, ...rest }) => rest); setOk(""); };
  const range = (key) => `${fmt(F[key].min)}–${fmt(F[key].max)}${unitOf(F[key])}`;

  const save = async (e) => {
    e.preventDefault();
    setOk("");
    const errs = validateSettings(f, spec);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/settings", {
        trial_days: Number(f.trial_days), anon_xray_per_day: Number(f.anon),
        crash_levels: String(f.crash).split(",").map((x) => Number(x.trim())).filter((x) => String(x) !== ""),
        scenario_rates: { bad: Number(f.bad), average: Number(f.average), good: Number(f.good) },
      });
      if (data) {
        qc.setQueryData(["admin", "settings", null], data);
        setF((cur) => ({ ...cur, crash: (data.crash_levels || []).join(", ") }));
      }
      qc.invalidateQueries({ queryKey: ["admin", "crash-notes"] });
      setOk("Saved.");
    } catch (e2) {
      const d = e2?.response?.data?.detail;
      if (d?.errors && typeof d.errors === "object") {
        const mapped = {};
        Object.entries(d.errors).forEach(([field, msg]) => { mapped[fromServer(field)] = msg; });
        setErrors(mapped);
      } else setErrors({ form: apiError(e2) });
    } finally { setBusy(false); }
  };
  return (
    <form onSubmit={save} noValidate className="space-y-4">
      <Card className="space-y-3">
        <Label>Accounts</Label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-[520px]">
          <Field label="Trial days (₹5,000 plan)" hint={`For new accounts. ${range("trial_days")}.`} error={errors.trial_days}>
            <Input type="number" inputMode="numeric" value={f.trial_days} onChange={set("trial_days")} aria-invalid={!!errors.trial_days} data-testid="settings-trial" />
          </Field>
          <Field label="X-Ray checks / day without login" hint={range("anon_xray_per_day")} error={errors.anon}>
            <Input type="number" inputMode="numeric" value={f.anon} onChange={set("anon")} aria-invalid={!!errors.anon} data-testid="settings-anon" />
          </Field>
        </div>
      </Card>
      <Card className="space-y-3">
        <Label>My Crypto Plan scenario rates for Bitcoin (% a year)</Label>
        <p className="text-[13px] text-bz-muted -mt-1">Shown to members as labelled assumptions, not predictions. Each plan scales them by its mix: Ethereum ×1.2, XRP ×1.4, Solana ×1.5, USDT doesn't grow. A bad crypto market loses money, so keep the bad case below zero. Each from {range("scenario_rates.bad")}.</p>
        <div className="grid grid-cols-3 gap-3 max-w-[520px]">
          <Field label="Bad" error={errors.bad}><Input type="number" inputMode="decimal" step="0.5" value={f.bad} onChange={set("bad")} aria-invalid={!!errors.bad} data-testid="settings-bad" /></Field>
          <Field label="Average" error={errors.average}><Input type="number" inputMode="decimal" step="0.5" value={f.average} onChange={set("average")} aria-invalid={!!errors.average} data-testid="settings-average" /></Field>
          <Field label="Good" error={errors.good}><Input type="number" inputMode="decimal" step="0.5" value={f.good} onChange={set("good")} aria-invalid={!!errors.good} data-testid="settings-good" /></Field>
        </div>
        {errors.rates && <p className="text-[12px] text-bz-miss" role="alert">{errors.rates}</p>}
      </Card>
      <Card className="space-y-3">
        <Label>Crash coach</Label>
        <Field label="Crash levels (% fall from the 30-day high)" error={errors.crash}
          hint={`Comma separated, each ${range("crash_levels")}, up to ${spec.max_crash_levels}. Write a note for each level under Crash notes.`}>
          <Input value={f.crash} onChange={set("crash")} className="max-w-[320px]" aria-invalid={!!errors.crash} data-testid="settings-crash" />
        </Field>
      </Card>
      {errors.form && <p className="text-sm text-bz-miss" role="alert">{errors.form}</p>}
      {Object.keys(errors).length > 0 && !errors.form && <p className="text-sm text-bz-miss" data-testid="settings-error">Nothing was saved. Fix the fields marked in red.</p>}
      <OkLine>{ok}</OkLine>
      <Button type="submit" loading={busy} data-testid="settings-save">Save settings</Button>
    </form>
  );
}

export default function AdminSettings() {
  const q = useAdmin("settings");
  const specQ = useAdmin("settings/spec", null, { staleTime: Infinity, retry: 1 });
  const spec = useMemo(() => specQ.data?.fields ? specQ.data : FALLBACK_SPEC, [specQ.data]);
  if (specQ.isLoading) return <AdminLoadable q={specQ} what="settings">{() => null}</AdminLoadable>;
  return <AdminLoadable q={q} what="settings">{(d) => <Editor s={d} spec={spec} />}</AdminLoadable>;
}
