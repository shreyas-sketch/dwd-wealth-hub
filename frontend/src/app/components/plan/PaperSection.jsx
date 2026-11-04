// Paper Money: value, P&L, positions, history chart, buy / sell (₹2,000 plan), reset.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Lock, Wallet } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { inr, inrShort, sdate } from "@/lib/format";

const Rs = ({ v }) => <><span className="sm:hidden">{inrShort(v)}</span><span className="hidden sm:inline">{inr(v)}</span></>;
import { AXIS_TICK, C, TOOLTIP } from "../chart";
import { Button, Card, Empty, ErrorCard, Field, Label, MoneyInput, Segmented, Select, Skeleton, Stat } from "../ui";
import { Move } from "../common";

const COINS = ["BTC", "ETH", "SOL", "XRP"];
const lakhAxis = (v) => (Math.abs(v) >= 1e5 ? `₹${(v / 1e5).toFixed(2)} L` : `₹${Math.round(v / 1000)}K`);

export function usePaper() {
  return useQuery({
    queryKey: ["paper"],
    queryFn: async () => {
      try { return (await api.get("/paper", { _silentGate: true })).data; }
      catch (e) { if (e?.response?.status === 404) return null; throw e; }
    },
  });
}

function HistoryChart({ history, start }) {
  const rows = (history || []).map((h) => ({ date: h.date, value: h.value_inr }));
  if (rows.length < 2) return <p className="text-[13px] text-bz-muted">The chart fills in day by day.</p>;
  const up = rows[rows.length - 1].value >= (start || rows[0].value);
  return (
    <div className="h-48 -mx-2" role="img" aria-label="Paper Money value over time">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <CartesianGrid stroke={C.line} vertical={false} />
          <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={false} minTickGap={36} tickFormatter={sdate} />
          <YAxis domain={["auto", "auto"]} tick={AXIS_TICK} tickLine={false} axisLine={false} width={64} tickFormatter={lakhAxis} />
          <Tooltip {...TOOLTIP} labelFormatter={sdate} formatter={(v) => [inr(v), "Value"]} />
          <Line type="monotone" dataKey="value" stroke={up ? C.accent : C.miss} strokeWidth={2.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TradeForm({ paper, onPaper }) {
  const held = (paper.positions || []).map((p) => p.symbol);
  const symbols = Array.from(new Set([...COINS, ...held]));
  const [f, setF] = useState({ symbol: "BTC", side: "buy", amount_inr: 5000 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  if (!paper.can_trade) {
    return (
      <Card inset className="flex items-start gap-3" data-testid="paper-locked">
        <Lock className="w-5 h-5 text-bz-gold-deep shrink-0 mt-0.5" aria-hidden />
        <div>
          <p className="font-semibold">Buying and selling with Paper Money is in the ₹2,000 plan.</p>
          <p className="text-[14px] text-bz-muted mt-0.5">You can still watch how your plan's practice money does every day.</p>
          <Link to="/app/plans?plan=lite&from=paper_trade" className="inline-block mt-2 text-sm font-semibold text-bz-accent">Upgrade to the ₹2,000 plan</Link>
        </div>
      </Card>
    );
  }
  const trade = async (e) => {
    e.preventDefault();
    setErr(""); setOk(""); setBusy(true);
    try {
      const { data } = await api.post("/paper/trade", { symbol: f.symbol, side: f.side, amount_inr: Number(f.amount_inr) });
      onPaper(data);
      if (f.side === "buy") setOk(`Bought ${inr(f.amount_inr)} of ${f.symbol} (practice).`);
      else {
        // The server sells at most what you hold: report the real amount from the cash that came back.
        const got = Math.max(0, Number(data?.cash_inr || 0) - Number(paper.cash_inr || 0));
        const all = !(data?.positions || []).some((x) => x.symbol === f.symbol);
        setOk(`Sold ${inr(got)} of ${f.symbol}${all ? ", all you held" : ""} (practice).`);
      }
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={trade} className="space-y-3" data-testid="paper-trade">
      <Label className="mb-0">Practice a trade</Label>
      <Segmented options={[{ value: "buy", label: "Buy" }, { value: "sell", label: "Sell" }]} value={f.side} onChange={(v) => setF({ ...f, side: v })} label="Buy or sell" testid="paper-side" />
      <div className="grid grid-cols-2 gap-2">
        <Field label="Coin"><Select value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value })} data-testid="paper-symbol">{symbols.map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="Amount"><MoneyInput value={f.amount_inr} onChange={(v) => setF({ ...f, amount_inr: v })} data-testid="paper-amount" /></Field>
      </div>
      <Button type="submit" className="w-full" loading={busy} disabled={!Number(f.amount_inr)} data-testid="paper-submit">{f.side === "buy" ? "Practice buy" : "Practice sell"}</Button>
      {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
      {ok && <p className="text-sm text-bz-accent font-semibold" role="status">{ok}</p>}
      <p className="text-[12px] text-bz-muted">Cash available: {inr(paper.cash_inr)}. Trades use the live price; no real money moves.</p>
    </form>
  );
}

export default function PaperSection({ selectedPlan }) {
  const qc = useQueryClient();
  const q = usePaper();
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const setPaper = (d) => { qc.setQueryData(["paper"], d); qc.invalidateQueries({ queryKey: ["plans"] }); };
  const act = async (kind) => {
    setErr(""); setBusy(kind);
    try {
      const { data } = kind === "start" ? await api.post("/paper/start", { plan_id: selectedPlan?.id }) : await api.post("/paper/reset");
      setPaper(data);
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };

  if (q.isLoading) return <Card><Skeleton lines={4} /></Card>;
  if (q.isError) return <ErrorCard error={q.error} onRetry={() => q.refetch()} what="Paper Money" />;
  const p = q.data;
  const started = p && (p.started_at || (p.positions || []).length);
  if (!started) {
    return (
      <Empty icon={Wallet} title="Practise your plan with ₹1,00,000 of paper money"
        sub="₹90,000 of pretend money goes in by your plan, and ₹10,000 stays as cash for practice trades. We track it at live prices, so you see how it feels before using real money."
        action={selectedPlan ? <Button onClick={() => act("start")} loading={busy === "start"} data-testid="paper-start">Start Paper Money on this plan</Button> : <span className="text-sm text-bz-muted">Make a plan first.</span>} />
    );
  }
  const up = Number(p.pnl_inr) >= 0;
  return (
    <div className="space-y-4" data-testid="paper-section">
      <Card>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <Label className="mb-1">Paper Money value</Label>
            <div className="font-bzserif text-[38px] font-semibold leading-none tabular">{inr(p.value_inr)}</div>
            <div className={`text-[15px] font-semibold mt-1.5 ${up ? "text-bz-accent" : "text-bz-miss"}`}>{up ? "+" : "−"}{inr(Math.abs(p.pnl_inr || 0))} (<Move v={p.pnl_pct} className="!font-semibold" />)</div>
          </div>
          {p.started_at && <span className="text-[12px] text-bz-muted">Started {sdate(p.started_at)} with {inr(p.start_inr)}</span>}
        </div>
        <div className="grid grid-cols-2 gap-2 mt-4">
          <Stat label="Cash" value={inr(p.cash_inr)} />
          <Stat label="In coins" value={inr((Number(p.value_inr) || 0) - (Number(p.cash_inr) || 0))} />
        </div>
        <div className="mt-4"><HistoryChart history={p.history} start={p.start_inr} /></div>
      </Card>
      {(p.positions || []).length > 0 && (
        <Card>
          <Label>Positions</Label>
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full text-[13px] sm:text-[14px] tabular sm:min-w-[420px]">
              <thead><tr className="text-left text-bz-muted font-bzmono text-[10.5px] uppercase tracking-[0.12em]">
                <th className="py-2 pr-2 font-medium">Coin</th><th className="py-2 px-2 font-medium text-right hidden sm:table-cell">Qty</th><th className="py-2 px-2 font-medium text-right">Avg price</th>
                <th className="py-2 px-2 font-medium text-right">Value</th><th className="py-2 pl-2 font-medium text-right">P&amp;L</th></tr></thead>
              <tbody>
                {p.positions.map((x) => (
                  <tr key={x.symbol} className="border-t border-bz-line">
                    <td className="py-2.5 pr-2 font-semibold">{x.symbol}</td>
                    <td className="py-2.5 px-2 text-right hidden sm:table-cell">{Number(x.qty || 0).toLocaleString("en-IN", { maximumFractionDigits: 6 })}</td>
                    <td className="py-2.5 px-2 text-right"><Rs v={x.avg_price_inr} /></td>
                    <td className="py-2.5 px-2 text-right"><Rs v={x.value_inr} /></td>
                    <td className="py-2.5 pl-2 text-right"><Move v={x.pnl_pct} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <Card><TradeForm paper={p} onPaper={setPaper} /></Card>
      <div className="flex flex-wrap gap-2 items-center">
        {selectedPlan && p.plan_id !== selectedPlan.id && <Button variant="quiet" onClick={() => act("start")} loading={busy === "start"}>Restart on "{selectedPlan.goal_name}"</Button>}
        <Button variant="small" onClick={() => { if (window.confirm("Start over with ₹1,00,000 of paper money?")) act("reset"); }} loading={busy === "reset"} data-testid="paper-reset">Reset paper money</Button>
      </div>
      {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
    </div>
  );
}
