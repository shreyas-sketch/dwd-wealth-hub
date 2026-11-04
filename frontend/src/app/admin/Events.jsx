// Admin › Events calendar.
import { hdate } from "@/lib/format";
import { Chip, Field, Input, Select } from "../components/ui";
import { CrudPage, textareaCls } from "./shared";

const KINDS = ["unlock", "listing", "upgrade", "halving", "macro", "etf"];
const blank = { date: "", title: "", kind: "unlock", coinsText: "", impact: "medium", note: "" };

function Form({ value: v, onChange }) {
  const set = (k) => (e) => onChange({ ...v, [k]: e.target.value });
  return (
    <div className="space-y-3">
      <Field label="Title"><Input value={v.title} onChange={set("title")} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Date"><Input type="date" value={v.date} onChange={set("date")} /></Field>
        <Field label="Kind"><Select value={v.kind} onChange={set("kind")}>{KINDS.map((k) => <option key={k} value={k}>{k}</option>)}</Select></Field>
        <Field label="Impact"><Select value={v.impact} onChange={set("impact")}>{["high", "medium", "low"].map((k) => <option key={k} value={k}>{k}</option>)}</Select></Field>
        <Field label="Coins" hint="Comma separated, e.g. BTC, ETH"><Input value={v.coinsText} onChange={set("coinsText")} /></Field>
      </div>
      <Field label="Note"><textarea className={textareaCls} rows={3} value={v.note} onChange={set("note")} /></Field>
    </div>
  );
}

export default function AdminEvents() {
  return (
    <CrudPage path="events" title="event" blank={blank} Form={Form} empty="No events yet."
      toForm={(r) => ({ ...blank, ...r, date: r.date ? String(r.date).slice(0, 10) : "", coinsText: (r.coins || []).join(", ") })}
      toBody={(v) => ({ date: v.date, title: v.title.trim(), kind: v.kind, impact: v.impact, note: v.note.trim(),
        coins: v.coinsText.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean) })}
      validate={(v) => (!v.title.trim() ? "Title is required." : !v.date ? "Date is required." : "")}
      cols={[
        { key: "date", label: "Date", render: (r) => hdate(r.date) },
        { key: "title", label: "Title", wrap: true, render: (r) => <b>{r.title}</b> },
        { key: "kind", label: "Kind" },
        { key: "impact", label: "Impact", render: (r) => <Chip tone={r.impact === "high" ? "bear" : r.impact === "medium" ? "gold" : "muted"}>{r.impact}</Chip> },
        { key: "coins", label: "Coins", render: (r) => (r.coins || []).join(", ") || "—" },
      ]} />
  );
}
