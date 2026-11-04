// What If: a monthly ₹ amount in BTC / ETH / SOL for 3 or 5 years → invested vs value today.
import { useEffect, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, apiError } from "@/lib/api";
import { track } from "@/lib/attribution";
import { inr, inrShort, monthLabel, pct } from "@/lib/format";
import { Button, Card, Chip, Field, Label, MoneyInput, Segmented, Skeleton } from "./ui";
import { AXIS_TICK, C, TOOLTIP } from "./chart";

const COINS = [{ value: "BTC", label: "Bitcoin" }, { value: "ETH", label: "Ethereum" }, { value: "SOL", label: "Solana" }];

function WhatIfChart({ series }) {
  const rows = (series || []).map((s) => ({ month: s.month, invested: s.invested_inr, value: s.value_inr }));
  if (rows.length < 2) return null;
  return (
    <div className="h-56 sm:h-64 -mx-2" role="img" aria-label="Money put in versus what it would be worth, month by month">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="wiValue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--bz-accent)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--bz-accent)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={C.line} vertical={false} />
          <XAxis dataKey="month" tick={AXIS_TICK} tickLine={false} axisLine={false} minTickGap={36} tickFormatter={monthLabel} />
          <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={56} tickFormatter={inrShort} />
          <Tooltip {...TOOLTIP} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n === "value" ? "Worth" : "Put in"]} />
          <Area type="monotone" dataKey="value" name="value" stroke={C.accent} strokeWidth={2.5} fill="url(#wiValue)" isAnimationActive={false} />
          <Line type="stepAfter" dataKey="invested" name="invested" stroke={C.muted} strokeWidth={1.75} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function WhatIfResult({ r }) {
  const up = Number(r.value_inr) >= Number(r.invested_inr);
  const w = r.worst;
  return (
    <div className="space-y-3 rise-in" data-testid="whatif-result">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-bzbtn border border-bz-line bg-bz-inset px-3.5 py-3">
          <div className="font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-muted">You put in</div>
          <div className="text-[22px] sm:text-[26px] font-semibold tabular mt-1">{inr(r.invested_inr)}</div>
        </div>
        <div className={`rounded-bzbtn border px-3.5 py-3 ${up ? "border-bz-accent bg-bz-accent-tint" : "border-bz-miss bg-bz-miss-tint"}`}>
          <div className="font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-muted">Worth today</div>
          <div className={`text-[22px] sm:text-[26px] font-semibold tabular mt-1 ${up ? "text-bz-accent" : "text-bz-miss"}`}>{inr(r.value_inr)}</div>
          <div className={`text-[13px] font-semibold ${up ? "text-bz-accent" : "text-bz-miss"}`}>{pct(r.return_pct)}</div>
        </div>
      </div>
      <WhatIfChart series={r.series} />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-bz-muted">
        <span className="inline-flex items-center gap-1.5"><span className="w-4 h-[3px] rounded bg-bz-accent" aria-hidden />What it was worth</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-4 border-t-2 border-dashed border-bz-muted" aria-hidden />What you had put in</span>
      </div>
      {w && (
        <Card inset data-testid="whatif-worst">
          <Label className="mb-1.5">The worst time to start</Label>
          <p className="text-[15px]">
            Starting in <b>{monthLabel(w.start)}</b>{w.note ? ` (${w.note.replace(/\.$/, "")})` : ""}: you'd have put in <b>{inr(w.invested_inr)}</b> and it would be worth <b className={Number(w.return_pct) >= 0 ? "text-bz-accent" : "text-bz-miss"}>{inr(w.value_inr)}</b> ({pct(w.return_pct)}).
          </p>
          <p className="text-[13px] text-bz-muted mt-1.5">Buying every month smooths out bad timing. It does not remove the risk.</p>
        </Card>
      )}
      <p className="text-[12px] text-bz-muted">{r.note || "Past prices, not a promise of future returns."}</p>
    </div>
  );
}

export default function WhatIf({ autoRun = true }) {
  const [f, setF] = useState({ monthly_inr: 5000, coin: "BTC", years: 5 });
  const [state, setState] = useState({ status: "idle" });
  const ran = useRef(false);

  const run = async (e) => {
    e?.preventDefault();
    const amount = Number(f.monthly_inr);
    if (!amount || amount < 100) { setState({ status: "error", msg: "Enter a monthly amount of ₹100 or more." }); return; }
    if (amount > 1000000) { setState({ status: "error", msg: "Enter a monthly amount up to ₹10,00,000." }); return; }
    setState((s) => ({ ...s, status: "loading" }));
    track("tool_opened", { tool: "whatif", coin: f.coin });
    try {
      const { data } = await api.post("/whatif", { monthly_inr: amount, coin: f.coin, years: f.years });
      setState({ status: "done", data: data || {} });
    } catch (err) {
      setState({ status: "error", msg: apiError(err) });
    }
  };

  useEffect(() => {
    if (autoRun && !ran.current) { ran.current = true; run(); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2"><Chip tone="gold">Past prices, not a promise</Chip></div>
      <form onSubmit={run} noValidate className="space-y-3">
        <Field label="Every month I put in">
          <MoneyInput value={f.monthly_inr} onChange={(v) => setF({ ...f, monthly_inr: v })} data-testid="whatif-amount" aria-label="Monthly amount in rupees" />
        </Field>
        <Field label="Into">
          <Segmented options={COINS} value={f.coin} onChange={(v) => setF({ ...f, coin: v })} label="Coin" testid="whatif-coin" />
        </Field>
        <Field label="For the last">
          <Segmented options={[{ value: 3, label: "3 years" }, { value: 5, label: "5 years" }]} value={f.years} onChange={(v) => setF({ ...f, years: v })} label="Years" testid="whatif-years" />
        </Field>
        <Button type="submit" className="w-full" data-testid="whatif-submit" loading={state.status === "loading"}>Show me</Button>
      </form>
      {state.status === "loading" && !state.data && <Skeleton lines={4} />}
      {state.status === "error" && <p className="text-sm text-bz-miss" role="alert">{state.msg}</p>}
      {state.data && <WhatIfResult r={state.data} />}
    </div>
  );
}
