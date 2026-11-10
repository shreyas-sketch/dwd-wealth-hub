// Admin › Baskets: coins + weight rows that must sum to 100.
import { Plus, X } from "lucide-react";
import { inr, sdate } from "@/lib/format";
import { Button, Field, Input, MoneyInput } from "../components/ui";
import { CrudPage, textareaCls } from "./shared";

const blank = { name: "", theme: "", description: "", coins: [{ symbol: "BTC", weight_pct: 50 }, { symbol: "ETH", weight_pct: 50 }], min_inr: 5000, risk_note: "", change_note: "", auto_rule: null };
const sum = (coins) => (coins || []).reduce((s, c) => s + (Number(c.weight_pct) || 0), 0);

function Form({ value: v, onChange }) {
  const set = (k) => (e) => onChange({ ...v, [k]: e.target.value });
  const setCoin = (i, k, val) => onChange({ ...v, coins: v.coins.map((c, j) => (j === i ? { ...c, [k]: val } : c)) });
  const total = sum(v.coins);
  return (
    <div className="space-y-3">
      <Field label="Name"><Input value={v.name} onChange={set("name")} /></Field>
      <Field label="Theme"><Input value={v.theme} onChange={set("theme")} placeholder="e.g. Blue chips, AI coins" /></Field>
      <Field label="Description"><textarea className={textareaCls} rows={3} value={v.description} onChange={set("description")} /></Field>
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[14px] font-semibold text-bz-muted">Coins and weights</span>
          <span className={`text-[13px] font-semibold tabular ${total === 100 ? "text-bz-accent" : "text-bz-miss"}`} data-testid="basket-weight-sum">Total {total}%{total === 100 ? "" : " (must be 100)"}</span>
        </div>
        <div className="space-y-2">
          {v.coins.map((c, i) => (
            <div key={i} className="flex gap-2 items-center">
              <Input value={c.symbol} onChange={(e) => setCoin(i, "symbol", e.target.value.toUpperCase())} placeholder="Symbol" className="flex-1" aria-label={`Coin ${i + 1} symbol`} />
              <div className="relative w-28">
                <Input type="number" min="0" max="100" value={c.weight_pct} onChange={(e) => setCoin(i, "weight_pct", e.target.value === "" ? "" : Number(e.target.value))} className="pr-7" aria-label={`Coin ${i + 1} weight`} />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-bz-muted">%</span>
              </div>
              <button type="button" aria-label="Remove coin" onClick={() => onChange({ ...v, coins: v.coins.filter((_, j) => j !== i) })} className="w-11 h-11 grid place-items-center rounded-bzbtn hover:bg-bz-miss-tint text-bz-miss"><X className="w-4 h-4" /></button>
            </div>
          ))}
        </div>
        <Button variant="small" className="mt-2" onClick={() => onChange({ ...v, coins: [...v.coins, { symbol: "", weight_pct: 0 }] })}><Plus className="w-3.5 h-3.5" aria-hidden /> Add coin</Button>
      </div>
      <Field label="Minimum amount"><MoneyInput value={v.min_inr} onChange={(val) => onChange({ ...v, min_inr: val })} /></Field>
      <Field label="Risk note"><textarea className={textareaCls} rows={2} value={v.risk_note} onChange={set("risk_note")} /></Field>
      <Field label="Change note" hint="Shown to holders when you change the coins or weights."><textarea className={textareaCls} rows={2} value={v.change_note} onChange={set("change_note")} /></Field>
      <label className="flex items-center gap-3 min-h-[44px] cursor-pointer">
        <input type="checkbox" checked={v.auto_rule === "top5"} onChange={(e) => onChange({ ...v, auto_rule: e.target.checked ? "top5" : null })} className="w-5 h-5 accent-[var(--bz-accent)]" data-testid="basket-auto-top5" />
        <span className="font-semibold">Refresh automatically</span><span className="text-sm text-bz-muted">On the first Monday of each month, the coins become the 5 largest on both Binance and KuCoin (35/20/15/15/15, no meme coins). Holders are told what changed.</span>
      </label>
    </div>
  );
}

export default function AdminBaskets() {
  return (
    <CrudPage path="baskets" title="basket" blank={blank} Form={Form} empty="No baskets yet."
      toForm={(r) => ({ ...blank, ...Object.fromEntries(Object.entries(r).filter(([, x]) => x != null)), coins: (r.coins || []).map((c) => ({ symbol: c.symbol, weight_pct: c.weight_pct })) })}
      toBody={(v) => ({ name: v.name.trim(), theme: v.theme.trim(), description: v.description.trim(),
        coins: v.coins.filter((c) => c.symbol).map((c) => ({ symbol: c.symbol.trim().toUpperCase(), weight_pct: Number(c.weight_pct) || 0 })),
        min_inr: Number(v.min_inr) || 0, risk_note: v.risk_note.trim(), change_note: v.change_note.trim(), auto_rule: v.auto_rule || null })}
      validate={(v) => {
        if (!v.name.trim()) return "Name is required.";
        const coins = v.coins.filter((c) => c.symbol);
        if (!coins.length) return "Add at least one coin.";
        if (new Set(coins.map((c) => c.symbol.toUpperCase())).size !== coins.length) return "Each coin can appear only once.";
        if (sum(coins) !== 100) return `Weights must add up to 100 (now ${sum(coins)}).`;
        return "";
      }}
      cols={[
        { key: "name", label: "Name", render: (r) => <><b>{r.name}</b>{r.auto_rule ? <span className="ml-2 text-[12px] text-bz-muted">Auto</span> : null}</> },
        { key: "theme", label: "Theme" },
        { key: "coins", label: "Coins", wrap: true, render: (r) => (r.coins || []).map((c) => `${c.symbol} ${c.weight_pct}%`).join(" · ") },
        { key: "min_inr", label: "Min", render: (r) => inr(r.min_inr), right: true },
        { key: "changed_at", label: "Changed", render: (r) => (r.changed_at ? sdate(r.changed_at) : "—") },
      ]} />
  );
}
