// Admin › Jobs: list, last run, Run now.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button, Card, Chip } from "../components/ui";
import { AdminLoadable, asList, dt, Table, useAdmin } from "./shared";

const short = (v) => {
  if (v == null) return "";
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 140 ? `${s.slice(0, 140)}…` : s;
};

export default function AdminJobs() {
  const qc = useQueryClient();
  const q = useAdmin("jobs");
  const [busy, setBusy] = useState(null);
  const [out, setOut] = useState({});
  const run = async (name) => {
    setBusy(name);
    try {
      const { data } = await api.post(`/admin/jobs/${encodeURIComponent(name)}/run`, null, { timeout: 300000 });
      setOut((o) => ({ ...o, [name]: { ok: data?.ok, text: short(data?.result) || (data?.ok ? "Done." : "Failed.") } }));
      qc.invalidateQueries({ queryKey: ["admin", "jobs"] });
    } catch (e) {
      setOut((o) => ({ ...o, [name]: { ok: false, text: apiError(e) } }));
    } finally { setBusy(null); }
  };
  return (
    <AdminLoadable q={q} what="jobs">
      {(d) => (
        <Card className="px-0 sm:px-5 py-2">
          <Table rows={asList(d)} empty="No jobs registered." cols={[
            { key: "name", label: "Job", wrap: true, render: (r) => <span><b>{r.label || r.name}</b>{r.label && <span className="block font-bzmono text-[11px] text-bz-muted">{r.name}</span>}</span> },
            { key: "schedule", label: "Schedule", wrap: true },
            { key: "last", label: "Last run", wrap: true, render: (r) => (r.last ? (
              <span className="block max-w-[340px]">
                <span className="flex items-center gap-2"><Chip tone={r.last.ok ? "bull" : "bear"}>{r.last.ok ? "ok" : "failed"}</Chip><span className="text-bz-muted">{dt(r.last.at)}</span></span>
                {r.last.result != null && <span className="block text-[12px] text-bz-muted mt-0.5 break-words">{short(r.last.result)}</span>}
              </span>
            ) : <span className="text-bz-muted">Never</span>) },
            { key: "run", label: "", render: (r) => (
              <span className="flex flex-col items-end gap-1">
                <Button variant="small" onClick={() => run(r.name)} loading={busy === r.name} data-testid={`job-run-${r.name}`}><Play className="w-3.5 h-3.5" aria-hidden /> Run now</Button>
                {out[r.name] && <span className={`text-[12px] max-w-[240px] whitespace-normal text-right ${out[r.name].ok ? "text-bz-accent" : "text-bz-miss"}`}>{out[r.name].text}</span>}
              </span>
            ) },
          ]} />
        </Card>
      )}
    </AdminLoadable>
  );
}
