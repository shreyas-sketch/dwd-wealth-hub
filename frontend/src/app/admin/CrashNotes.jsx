// Admin › Crash notes: one note per crash level (levels from Settings).
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Button, Card, Label, OkLine } from "../components/ui";
import { AdminLoadable, textareaCls, useAdmin } from "./shared";

function Editor({ notes, levels }) {
  const qc = useQueryClient();
  const all = Array.from(new Set([...(levels || []), ...notes.map((n) => n.level)])).filter((x) => x != null).sort((a, b) => a - b);
  const [vals, setVals] = useState(() => Object.fromEntries(all.map((l) => [l, notes.find((n) => n.level === l)?.note || ""])));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const save = async () => {
    setErr(""); setOk(""); setBusy(true);
    try {
      await api.post("/admin/crash-notes", { notes: all.map((l) => ({ level: l, note: (vals[l] || "").trim() })) });
      setOk("Saved."); qc.invalidateQueries({ queryKey: ["admin", "crash-notes"] });
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  if (!all.length) return <Card inset><p className="text-sm">No crash levels set. Add them in Settings first.</p></Card>;
  return (
    <Card className="space-y-4">
      <p className="text-[14px] text-bz-muted">When Bitcoin falls this much from its 30-day high, ₹5,000 members get an alert with your note (at most once per level per week). Write it the way you'd say it on a call.</p>
      {all.map((l) => (
        <div key={l}>
          <Label className="mb-1.5">Down {l}% or more</Label>
          <textarea className={textareaCls} rows={3} value={vals[l] || ""} onChange={(e) => setVals({ ...vals, [l]: e.target.value })} data-testid={`crash-note-${l}`} />
        </div>
      ))}
      {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
      <OkLine>{ok}</OkLine>
      <Button onClick={save} loading={busy} data-testid="crash-save">Save notes</Button>
    </Card>
  );
}

export default function AdminCrashNotes() {
  const q = useAdmin("crash-notes");
  const s = useAdmin("settings");
  return (
    <AdminLoadable q={q} what="crash notes">
      {(d) => (s.isLoading ? null : <Editor notes={d.notes || []} levels={s.data?.crash_levels || [20, 30, 40]} />)}
    </AdminLoadable>
  );
}
