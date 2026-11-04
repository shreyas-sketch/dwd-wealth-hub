// Admin › Airdrops: table + add/edit sheet + delete. Steps are one per line.
import { hdate } from "@/lib/format";
import { Chip, Field, Input, Select } from "../components/ui";
import { XrayChip } from "../components/common";
import { CrudPage, textareaCls } from "./shared";

const blank = { name: "", coin: "", chain: "", status: "live", reward: "", deadline: "", link: "", description: "", stepsText: "" };

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
      <Field label="Steps (one per line)"><textarea className={textareaCls} rows={5} value={v.stepsText} onChange={set("stepsText")} placeholder={"Create a wallet\nBridge a small amount\nMake one swap"} /></Field>
    </div>
  );
}

export default function AdminAirdrops() {
  return (
    <CrudPage path="airdrops" title="airdrop" blank={blank} Form={Form} empty="No airdrops yet."
      toForm={(r) => ({ ...blank, ...r, deadline: r.deadline ? String(r.deadline).slice(0, 10) : "", stepsText: (r.steps || []).map((s) => s.text).join("\n"), _steps: r.steps || [] })}
      toBody={(v) => {
        const lines = v.stepsText.split("\n").map((s) => s.trim()).filter(Boolean);
        const old = v._steps || [];
        const steps = lines.map((text, i) => ({ id: old[i]?.id || `s${i + 1}`, text }));
        return { name: v.name.trim(), coin: v.coin.trim(), chain: v.chain.trim(), status: v.status, reward: v.reward.trim(),
          deadline: v.deadline || null, link: v.link.trim(), description: v.description.trim(), steps };
      }}
      validate={(v) => (!v.name.trim() ? "Name is required." : v.link && !/^https?:\/\//.test(v.link.trim()) ? "The link must start with http:// or https://" : "")}
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
