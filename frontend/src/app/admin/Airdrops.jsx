// Admin › Airdrops: table + add/edit sheet + delete.
//
// Steps are edited as a list of rows, and each row carries its step id, so moving, inserting or deleting a step
// keeps members' ticks on the right step (QA 3 Nov: ids used to be assigned by line position). New rows have no id;
// the server assigns one. Pasting several lines into a step splits them into separate steps.
import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import { hdate } from "@/lib/format";
import { Button, Chip, Field, Input, Select } from "../components/ui";
import { XrayChip } from "../components/common";
import { CrudPage, textareaCls } from "./shared";

let rowSeq = 0;
const newRow = (text = "", id = null) => ({ key: `r${++rowSeq}`, id, text });

const blank = { name: "", coin: "", chain: "", status: "live", reward: "", deadline: "", link: "", description: "", steps: [] };

function StepsEditor({ rows, onChange }) {
  const update = (i, patch) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= rows.length) return;
    const next = rows.slice();
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  const remove = (i) => onChange(rows.filter((_, j) => j !== i));
  const onPaste = (i) => (e) => {
    const text = e.clipboardData?.getData("text") || "";
    const lines = text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    if (lines.length < 2) return;
    e.preventDefault();
    const [first, ...rest] = lines;
    const next = rows.slice();
    next[i] = { ...next[i], text: first };
    next.splice(i + 1, 0, ...rest.map((t) => newRow(t)));
    onChange(next);
  };
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[14px] font-semibold text-bz-muted">Steps</span>
        <span className="text-[12px] text-bz-muted">Members' ticks stay with each step when you reorder.</span>
      </div>
      {rows.length === 0 && <p className="text-[13px] text-bz-muted mb-2">No steps yet.</p>}
      <ol className="space-y-2" data-testid="airdrop-steps">
        {rows.map((r, i) => (
          <li key={r.key} className="flex gap-1.5 items-center">
            <span className="w-6 text-right text-[14px] font-semibold text-bz-muted tabular shrink-0">{i + 1}.</span>
            <Input value={r.text} onChange={(e) => update(i, { text: e.target.value })} onPaste={onPaste(i)}
              placeholder="e.g. Create a wallet" className="flex-1 min-w-0" aria-label={`Step ${i + 1}`} data-testid={`airdrop-step-${i}`} />
            <button type="button" aria-label={`Move step ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}
              className="w-9 h-11 grid place-items-center rounded-bzbtn hover:bg-bz-inset disabled:opacity-30" data-testid={`airdrop-step-up-${i}`}><ArrowUp className="w-4 h-4" aria-hidden /></button>
            <button type="button" aria-label={`Move step ${i + 1} down`} disabled={i === rows.length - 1} onClick={() => move(i, 1)}
              className="w-9 h-11 grid place-items-center rounded-bzbtn hover:bg-bz-inset disabled:opacity-30"><ArrowDown className="w-4 h-4" aria-hidden /></button>
            <button type="button" aria-label={`Remove step ${i + 1}`} onClick={() => remove(i)}
              className="w-9 h-11 grid place-items-center rounded-bzbtn hover:bg-bz-miss-tint text-bz-miss"><X className="w-4 h-4" aria-hidden /></button>
          </li>
        ))}
      </ol>
      <Button variant="small" className="mt-2" onClick={() => onChange([...rows, newRow()])} data-testid="airdrop-add-step"><Plus className="w-3.5 h-3.5" aria-hidden /> Add step</Button>
    </div>
  );
}

function Form({ value: v, onChange }) {
  const set = (k) => (e) => onChange({ ...v, [k]: e.target.value });
  return (
    <div className="space-y-3">
      <Field label="Name"><Input value={v.name} onChange={set("name")} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Coin / token"><Input value={v.coin} onChange={set("coin")} /></Field>
        <Field label="Chain"><Input value={v.chain} onChange={set("chain")} placeholder="Ethereum, Solana…" /></Field>
        <Field label="Status"><Select value={v.status} onChange={set("status")}><option value="live">Live</option><option value="ended">Ended</option></Select></Field>
        <Field label="Deadline"><Input type="date" value={v.deadline} onChange={set("deadline")} /></Field>
      </div>
      <Field label="Reward"><Input value={v.reward} onChange={set("reward")} placeholder="e.g. Up to 500 XYZ tokens" /></Field>
      <Field label="Link" hint="The official airdrop page. It is X-Rayed when you save."><Input type="url" value={v.link} onChange={set("link")} placeholder="https://" /></Field>
      <Field label="Description"><textarea className={textareaCls} rows={3} value={v.description} onChange={set("description")} /></Field>
      <StepsEditor rows={v.steps} onChange={(steps) => onChange({ ...v, steps })} />
    </div>
  );
}

export default function AdminAirdrops() {
  return (
    <CrudPage path="airdrops" title="airdrop" blank={blank} Form={Form} empty="No airdrops yet."
      toForm={(r) => ({ ...blank, ...r, coin: r.coin || "", chain: r.chain || "", reward: r.reward || "", link: r.link || "",
        description: r.description || "", deadline: r.deadline ? String(r.deadline).slice(0, 10) : "",
        steps: (r.steps || []).map((s) => newRow(s.text, s.id)) })}
      toBody={(v) => ({
        name: v.name.trim(), coin: v.coin.trim(), chain: v.chain.trim(), status: v.status, reward: v.reward.trim(),
        deadline: v.deadline || null, link: v.link.trim(), description: v.description.trim(),
        steps: v.steps.map((s) => ({ ...(s.id ? { id: s.id } : {}), text: s.text.trim() })).filter((s) => s.text),
      })}
      validate={(v) => (!v.name.trim() ? "Name is required."
        : v.link && !/^https?:\/\//.test(v.link.trim()) ? "The link must start with http:// or https://"
        : v.steps.filter((s) => s.text.trim()).length > 30 ? "Use at most 30 steps." : "")}
      cols={[
        { key: "name", label: "Name", render: (r) => <b>{r.name}</b> },
        { key: "coin", label: "Coin" },
        { key: "status", label: "Status", render: (r) => <Chip tone={r.status === "live" ? "bull" : "muted"}>{r.status}</Chip> },
        { key: "deadline", label: "Deadline", render: (r) => (r.deadline ? hdate(r.deadline) : "—") },
        { key: "steps", label: "Steps", render: (r) => (r.steps || []).length, right: true },
        { key: "xray", label: "X-Ray", render: (r) => (r.xray ? <XrayChip label={r.xray.label} score={r.xray.score} /> : "—") },
      ]} />
  );
}
