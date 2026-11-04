// Admin › Features: flag toggles grouped, source shown. POST /admin/flags {key, on: true|false|null}.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Card, Chip, Label } from "../components/ui";
import { AdminLoadable, asList, useAdmin } from "./shared";

const SOURCE = { admin: "Set here", environment: "Server setting", default: "Built-in default" };

export default function AdminFeatures() {
  const qc = useQueryClient();
  const q = useAdmin("flags");
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const set = async (key, on) => {
    setErr(""); setBusy(key);
    try {
      const { data } = await api.post("/admin/flags", { key, on });
      if (data) qc.setQueryData(["admin", "flags", null], data); else qc.invalidateQueries({ queryKey: ["admin", "flags"] });
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };
  return (
    <AdminLoadable q={q} what="feature switches">
      {(d) => {
        const groups = {};
        asList(d).forEach((f) => { const g = f.group || "Other"; (groups[g] = groups[g] || []).push(f); });
        return (
          <div className="space-y-3">
            <Card inset><p className="text-sm">Switch a feature on or off for everyone. "Back to default" hands the switch back to the server setting.</p></Card>
            {Object.keys(groups).length === 0 && <p className="text-sm text-bz-muted">No switches.</p>}
            {Object.entries(groups).map(([g, fs]) => (
              <Card key={g}>
                <Label>{g}</Label>
                <ul className="divide-y divide-bz-line">
                  {fs.map((f) => (
                    <li key={f.key} className="flex items-start justify-between gap-4 py-3" data-testid={`flag-${f.key}`}>
                      <div className="min-w-0">
                        <div className="font-semibold">{f.label || f.key}</div>
                        {f.description && <p className="text-sm text-bz-muted mt-0.5">{f.description}</p>}
                        <p className="text-xs text-bz-muted mt-1.5 flex items-center gap-2 flex-wrap">
                          <Chip tone={f.source === "admin" ? "gold" : "muted"}>{SOURCE[f.source] || f.source || "—"}</Chip>
                          <span className="font-bzmono">{f.key}</span>
                          {f.source === "admin" && <button type="button" className="text-bz-accent font-semibold" onClick={() => set(f.key, null)}>Back to default</button>}
                        </p>
                      </div>
                      <button type="button" role="switch" aria-checked={!!f.on} aria-label={f.label || f.key} disabled={busy === f.key} onClick={() => set(f.key, !f.on)}
                        className={`relative shrink-0 w-12 h-7 rounded-full border transition-colors disabled:opacity-60 ${f.on ? "bg-bz-accent border-bz-accent" : "bg-bz-inset border-bz-line-strong"}`}>
                        <span className={`absolute top-0.5 left-0.5 w-[22px] h-[22px] rounded-full bg-white shadow transition-transform ${f.on ? "translate-x-5" : ""}`} />
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
            {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
          </div>
        );
      }}
    </AdminLoadable>
  );
}
