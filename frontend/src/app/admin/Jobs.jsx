// Admin › Jobs: list, last run, Run now.
// Each run shows the server's one-line `summary` ("3 plans bought, 1 failed."); the raw values are behind
// "Details" as a key/value list for debugging (QA 3 Nov: raw JSON was shown).
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button, Card, Chip } from "../components/ui";
import { AdminLoadable, asList, dt, Table, useAdmin } from "./shared";

const label = (k) => String(k).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const show = (v) => {
  if (v == null) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return v.toLocaleString("en-IN");
  if (Array.isArray(v)) return v.length ? v.map(show).join(", ") : "none";
  if (typeof v === "object") return Object.entries(v).map(([k, x]) => `${label(k)}: ${show(x)}`).join(" · ");
  if (/^\d{4}-\d{2}-\d{2}T/.test(v)) return dt(v);
  return String(v);
};

function Details({ result, ms }) {
  const [open, setOpen] = useState(false);
  if (result == null || typeof result !== "object") return null;
  return (
    <span className="block mt-0.5">
      <button type="button" className="text-[12px] text-bz-accent font-semibold" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? "Hide details" : "Details"}
      </button>
      {open && (
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[12px]">
          {Object.entries(result).map(([k, v]) => (
            <span key={k} className="contents"><dt className="text-bz-muted">{label(k)}</dt><dd className="break-words">{show(v)}</dd></span>
          ))}
          {ms != null && <span className="contents"><dt className="text-bz-muted">Took</dt><dd>{(ms / 1000).toFixed(1)} s</dd></span>}
        </dl>
      )}
    </span>
  );
}

export default function AdminJobs() {
  const qc = useQueryClient();
  const q = useAdmin("jobs");
  const [busy, setBusy] = useState(null);
  const [out, setOut] = useState({});
  const run = async (name) => {
    setBusy(name);
    try {
      const { data } = await api.post(`/admin/jobs/${encodeURIComponent(name)}/run`, null, { timeout: 300000 });
      setOut((o) => ({ ...o, [name]: { ok: data?.ok, text: data?.summary || (data?.ok ? "Done." : "Failed.") } }));
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
              <span className="block max-w-[340px]" data-testid={`job-last-${r.name}`}>
                <span className="flex items-center gap-2"><Chip tone={r.last.ok ? "bull" : "bear"}>{r.last.ok ? "ok" : "failed"}</Chip><span className="text-bz-muted">{dt(r.last.at)}</span></span>
                {r.last.summary && <span className="block text-[13px] mt-0.5 break-words">{r.last.summary}</span>}
                <Details result={r.last.result} ms={r.last.ms} />
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
