// Admin › Settings: trial days, scenario rates (% a year), crash levels, anonymous X-Ray per day.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Button, Card, Field, Input, Label, OkLine } from "../components/ui";
import { AdminLoadable, useAdmin } from "./shared";

function Editor({ s }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    trial_days: s.trial_days ?? 3,
    bad: s.scenario_rates?.bad ?? 0, average: s.scenario_rates?.average ?? 15, good: s.scenario_rates?.good ?? 35,
    crash: (s.crash_levels || [20, 30, 40]).join(", "),
    anon: s.anon_xray_per_day ?? 1,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const num = (k) => (e) => setF({ ...f, [k]: e.target.value === "" ? "" : Number(e.target.value) });
  const save = async (e) => {
    e.preventDefault();
    setErr(""); setOk("");
    const levels = f.crash.split(",").map((x) => Number(x.trim())).filter((x) => Number.isFinite(x) && x > 0);
    if (!levels.length) { setErr("Add at least one crash level, e.g. 20, 30, 40."); return; }
    if ([f.trial_days, f.bad, f.average, f.good, f.anon].some((x) => x === "" || !Number.isFinite(Number(x)))) { setErr("Fill in every number."); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/admin/settings", {
        trial_days: Number(f.trial_days), anon_xray_per_day: Number(f.anon), crash_levels: levels,
        scenario_rates: { bad: Number(f.bad), average: Number(f.average), good: Number(f.good) },
      });
      if (data) qc.setQueryData(["admin", "settings", null], data);
      qc.invalidateQueries({ queryKey: ["admin", "crash-notes"] });
      setOk("Saved.");
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={save} className="space-y-4">
      <Card className="space-y-3">
        <Label>Accounts</Label>
        <div className="grid grid-cols-2 gap-3 max-w-[520px]">
          <Field label="Trial days (₹5,000 plan)" hint="For new accounts."><Input type="number" min="0" max="30" value={f.trial_days} onChange={num("trial_days")} data-testid="settings-trial" /></Field>
          <Field label="X-Ray checks / day without login"><Input type="number" min="0" max="20" value={f.anon} onChange={num("anon")} data-testid="settings-anon" /></Field>
        </div>
      </Card>
      <Card className="space-y-3">
        <Label>My Crypto Plan scenario rates (% a year)</Label>
        <p className="text-[13px] text-bz-muted -mt-1">Shown to members as labelled assumptions, not predictions.</p>
        <div className="grid grid-cols-3 gap-3 max-w-[520px]">
          <Field label="Bad"><Input type="number" step="0.5" value={f.bad} onChange={num("bad")} data-testid="settings-bad" /></Field>
          <Field label="Average"><Input type="number" step="0.5" value={f.average} onChange={num("average")} data-testid="settings-average" /></Field>
          <Field label="Good"><Input type="number" step="0.5" value={f.good} onChange={num("good")} data-testid="settings-good" /></Field>
        </div>
      </Card>
      <Card className="space-y-3">
        <Label>Crash coach</Label>
        <Field label="Crash levels (% fall from the 30-day high)" hint="Comma separated. Write a note for each level under Crash notes.">
          <Input value={f.crash} onChange={(e) => setF({ ...f, crash: e.target.value })} className="max-w-[320px]" data-testid="settings-crash" />
        </Field>
      </Card>
      {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
      <OkLine>{ok}</OkLine>
      <Button type="submit" loading={busy} data-testid="settings-save">Save settings</Button>
    </form>
  );
}

export default function AdminSettings() {
  const q = useAdmin("settings");
  return <AdminLoadable q={q} what="settings">{(d) => <Editor s={d} />}</AdminLoadable>;
}
