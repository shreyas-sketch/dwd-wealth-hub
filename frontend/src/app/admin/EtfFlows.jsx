// Admin › ETF flows: date, net $ millions, note. (Contract: GET list / POST add.)
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { hdate, istToday } from "@/lib/format";
import { Button, Card, Field, Input, Label, OkLine } from "../components/ui";
import { AdminLoadable, asList, Table, useAdmin } from "./shared";

export default function AdminEtfFlows() {
  const qc = useQueryClient();
  const q = useAdmin("etf-flows");
  const [f, setF] = useState({ date: istToday(), net_usd_m: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const add = async (e) => {
    e.preventDefault();
    setErr(""); setOk("");
    if (f.net_usd_m === "" || Number.isNaN(Number(f.net_usd_m))) { setErr("Enter the net flow in $ millions (negative for outflows)."); return; }
    setBusy(true);
    try {
      await api.post("/admin/etf-flows", { date: f.date, net_usd_m: Number(f.net_usd_m), note: f.note.trim() });
      setOk("Saved."); setF({ ...f, net_usd_m: "", note: "" });
      qc.invalidateQueries({ queryKey: ["admin", "etf-flows"] });
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <Card>
        <Label>Add a day</Label>
        <form onSubmit={add} className="grid gap-3 sm:grid-cols-[160px_160px_1fr_auto] items-end">
          <Field label="Date"><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          <Field label="Net ($ millions)"><Input type="number" step="0.1" inputMode="decimal" value={f.net_usd_m} onChange={(e) => setF({ ...f, net_usd_m: e.target.value })} placeholder="e.g. -120.5" data-testid="etf-net" /></Field>
          <Field label="Note"><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="e.g. IBIT led inflows" /></Field>
          <Button type="submit" loading={busy} data-testid="etf-save">Save</Button>
        </form>
        {err && <p className="text-sm text-bz-miss mt-2" role="alert">{err}</p>}
        <OkLine>{ok}</OkLine>
        <p className="text-[12px] text-bz-muted mt-2">The latest day shows in Market Pulse.</p>
      </Card>
      <AdminLoadable q={q} what="ETF flows">
        {(d) => (
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={asList(d).slice().sort((a, b) => String(b.date).localeCompare(String(a.date)))} empty="No ETF flows yet." cols={[
              { key: "date", label: "Date", render: (r) => hdate(r.date) },
              { key: "net_usd_m", label: "Net $m", right: true, render: (r) => <span className={Number(r.net_usd_m) >= 0 ? "text-bz-accent font-semibold" : "text-bz-miss font-semibold"}>{Number(r.net_usd_m) >= 0 ? "+" : ""}{Number(r.net_usd_m).toLocaleString("en-US")}</span> },
              { key: "note", label: "Note", wrap: true },
            ]} />
          </Card>
        )}
      </AdminLoadable>
    </div>
  );
}
