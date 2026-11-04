// Admin › Monday Picks: suggest button, two rows symbol + reasoning, publish toggle.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { istToday } from "@/lib/format";
import { Button, Card, Field, Input, Label, OkLine } from "../components/ui";
import { AdminLoadable, textareaCls, useAdmin } from "./shared";

function mondayOf() {   // Monday of this week in India (the backend's week_of)
  const x = new Date(`${istToday()}T00:00:00Z`); const day = (x.getUTCDay() + 6) % 7; x.setUTCDate(x.getUTCDate() - day);
  return x.toISOString().slice(0, 10);
}
const EMPTY_ROWS = [{ symbol: "", reasoning: "" }, { symbol: "", reasoning: "" }];

function Editor({ data }) {
  const qc = useQueryClient();
  const [weekOf, setWeekOf] = useState(data.week_of ? String(data.week_of).slice(0, 10) : mondayOf());
  const [published, setPublished] = useState(!!data.published);
  const [rows, setRows] = useState(() => {
    const p = (data.picks || []).map((x) => ({ symbol: x.symbol || "", reasoning: x.reasoning || "" }));
    return [...p, ...EMPTY_ROWS].slice(0, 2);
  });
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const setRow = (i, k, v) => setRows((r) => r.map((x, j) => (j === i ? { ...x, [k]: v } : x)));

  const suggest = async () => {
    setErr(""); setOk(""); setBusy("suggest");
    try {
      const { data: s } = await api.get("/admin/picks/suggest");
      const list = Array.isArray(s) ? s : s?.picks || s?.items || s?.suggestions || [];
      if (!list.length) { setErr("No suggestions right now."); return; }
      setRows([0, 1].map((i) => ({
        symbol: list[i]?.symbol || rows[i].symbol,
        reasoning: list[i]?.reasoning || list[i]?.summary || rows[i].reasoning,
      })));
      setOk("Filled with today's top two Bullish coins. Edit the reasoning before publishing.");
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };
  const save = async () => {
    setErr(""); setOk("");
    const picks = rows.filter((r) => r.symbol.trim()).map((r) => ({ symbol: r.symbol.trim().toUpperCase(), reasoning: r.reasoning.trim() }));
    if (published && picks.length < 2) { setErr("Add two coins before publishing."); return; }
    if (picks.some((p) => !p.reasoning)) { setErr("Every pick needs reasoning."); return; }
    setBusy("save");
    try {
      await api.post("/admin/picks", { week_of: weekOf, published, picks });
      setOk(published ? "Published. Members see the picks now." : "Saved as a draft.");
      qc.invalidateQueries({ queryKey: ["admin", "picks"] });
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-end gap-3 justify-between">
        <Field label="Week of (Monday)" className="w-52"><Input type="date" value={weekOf} onChange={(e) => setWeekOf(e.target.value)} /></Field>
        <Button variant="quiet" onClick={suggest} loading={busy === "suggest"} data-testid="picks-suggest"><Sparkles className="w-4 h-4" aria-hidden /> Suggest</Button>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="rounded-bzbtn border border-bz-line p-3 space-y-2">
          <Label className="mb-0">Pick {i + 1}</Label>
          <Field label="Symbol"><Input value={r.symbol} onChange={(e) => setRow(i, "symbol", e.target.value.toUpperCase())} placeholder="e.g. SOL" data-testid={`pick-symbol-${i}`} /></Field>
          <Field label="Reasoning (plain words)"><textarea className={textareaCls} rows={3} value={r.reasoning} onChange={(e) => setRow(i, "reasoning", e.target.value)} data-testid={`pick-reasoning-${i}`} /></Field>
        </div>
      ))}
      <label className="flex items-center gap-3 min-h-[44px] cursor-pointer">
        <input type="checkbox" checked={published} onChange={(e) => setPublished(e.target.checked)} className="w-5 h-5 accent-[var(--bz-accent)]" data-testid="picks-published" />
        <span className="font-semibold">Published</span><span className="text-sm text-bz-muted">Members see the picks only when this is on.</span>
      </label>
      {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
      <OkLine>{ok}</OkLine>
      <Button className="w-full sm:w-auto" onClick={save} loading={busy === "save"} data-testid="picks-save">Save</Button>
    </Card>
  );
}

export default function AdminPicks() {
  const q = useAdmin("picks");
  return <AdminLoadable q={q} what="Monday Picks">{(d) => <Editor data={d} />}</AdminLoadable>;
}
