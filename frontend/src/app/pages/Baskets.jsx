// /app/baskets — ready-made coin groups: Practice (paper), Invest now (venue + amount, 409 short_usdt), Monthly autopilot.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers } from "lucide-react";
import { useFeature } from "@/context/AuthContext";
import { api, apiError, errCode } from "@/lib/api";
import { inr, sdate, usd, venueName } from "@/lib/format";
import WeightBar from "../components/WeightBar";
import { Button, Card, Chip, Empty, Field, Label, Loadable, MoneyInput, PageHeader, Sheet } from "../components/ui";
import { Gate } from "../components/common";
import { ScheduleFields, scheduleBody, VenuePicker } from "../components/Dca";
import { useConfirm } from "../components/Confirm";

function useAutopilotInfo() {
  return useQuery({ queryKey: ["autopilot"], queryFn: async () => (await api.get("/autopilot", { _silentGate: true })).data });
}

function PracticeSheet({ b, onClose }) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState(Math.max(b.min_inr || 0, 10000));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(null);
  const go = async () => {
    setErr(""); setBusy(true);
    try { const { data } = await api.post(`/baskets/${b.id}/practice`, { amount_inr: Number(amount) }); qc.setQueryData(["paper"], data); setDone(data); }
    catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <Sheet open onClose={onClose} title={`Practise ${b.name}`}>
      {done ? (
        <div className="space-y-3">
          <p className="text-[16px] font-semibold text-bz-accent">Done. {inr(amount)} of paper money is now in {b.name}.</p>
          <p className="text-[14px] text-bz-muted">Paper Money value: {inr(done.value_inr)}.</p>
          <Link to="/app/plan" className="block"><Button className="w-full">See my Paper Money</Button></Link>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-[15px]">Buy this basket with practice money from your Paper Money account. No real money moves.</p>
          <Field label="Practice amount"><MoneyInput value={amount} onChange={setAmount} data-testid="basket-practice-amount" /></Field>
          {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
          <Button className="w-full" onClick={go} loading={busy} disabled={!Number(amount)} data-testid="basket-practice-go">Practise with {inr(amount)}</Button>
        </div>
      )}
    </Sheet>
  );
}

function InvestSheet({ b, onClose }) {
  const confirm = useConfirm();
  const ap = useAutopilotInfo();
  const venues = ap.data?.venues || [];
  const linked = venues.filter((v) => v.linked);
  const [venue, setVenue] = useState(null);
  const [amount, setAmount] = useState(b.min_inr || 5000);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [short, setShort] = useState(null);
  const [done, setDone] = useState(null);
  const v = venue || linked[0]?.venue;
  const go = async () => {
    setErr(""); setShort(null);
    if (b.min_inr && Number(amount) < b.min_inr) { setErr(`The smallest amount for this basket is ${inr(b.min_inr)}.`); return; }
    if (!(await confirm({ title: `Buy ${inr(amount)} of ${b.name}?`, confirmLabel: `Buy ${inr(amount)} now`,
      body: `This places real orders on your ${venueName(v)} account using your USDT. It can't be undone from here.` }))) return;
    setBusy(true);
    try { const { data } = await api.post(`/baskets/${b.id}/invest`, { venue: v, amount_inr: Number(amount) }); setDone(data || {}); }
    catch (e) {
      if (e?.response?.status === 409 || errCode(e) === "short_usdt") setShort(e?.response?.data?.detail || {});
      else setErr(apiError(e));
    } finally { setBusy(false); }
  };
  return (
    <Sheet open onClose={onClose} title={`Invest in ${b.name}`}>
      {done ? (
        <div className="space-y-3" data-testid="basket-invest-done">
          <p className="text-[16px] font-semibold text-bz-accent">Orders placed for {inr(done.total_inr)}.</p>
          <ul className="divide-y divide-bz-line text-[14px]">
            {(done.orders || []).map((o, i) => (
              <li key={`${o.symbol}-${i}`} className="py-2 flex justify-between gap-2">
                <span><b>{o.symbol}</b> · {inr(o.inr)}</span>
                <span className="text-bz-muted tabular">{o.qty != null ? `${Number(o.qty).toLocaleString("en-IN", { maximumFractionDigits: 6 })} @ ${usd(o.price_usd)}` : ""} <Chip tone={o.status === "filled" || o.status === "done" ? "bull" : o.status === "failed" ? "bear" : "muted"}>{o.status}</Chip></span>
              </li>
            ))}
          </ul>
          <Button className="w-full" variant="secondary" onClick={onClose}>Close</Button>
        </div>
      ) : ap.isLoading ? <p className="text-sm text-bz-muted">Loading your exchanges…</p> : !linked.length ? (
        <div className="space-y-3">
          <p className="text-[15px]">To buy for real, link your KuCoin or Binance account first (trade-only key).</p>
          <Link to="/app/autopilot" className="block"><Button className="w-full">Link an exchange</Button></Link>
        </div>
      ) : (
        <div className="space-y-4">
          <VenuePicker venues={venues} value={v} onChange={setVenue} />
          <Field label="Amount" hint={b.min_inr ? `At least ${inr(b.min_inr)}. Split across the coins by weight.` : "Split across the coins by weight."}>
            <MoneyInput value={amount} onChange={setAmount} data-testid="basket-invest-amount" />
          </Field>
          {short && (
            <div className="rounded-bzbtn border border-bz-miss bg-bz-miss-tint px-3.5 py-3 text-[14px]" role="alert" data-testid="basket-short-usdt">
              <p className="font-semibold text-bz-miss">Not enough USDT in your {venueName(v)} account.</p>
              <p className="mt-1">{short.msg || "Add USDT to your exchange, then try again."} Use the <Link to="/app/p2p" className="font-semibold text-bz-accent">P2P Rate Finder</Link> to buy USDT at a good rate.</p>
            </div>
          )}
          {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
          <Button className="w-full" onClick={go} loading={busy} disabled={!Number(amount)} data-testid="basket-invest-go">Buy {inr(amount)} now</Button>
          <p className="text-[12px] text-bz-muted">Market orders from your own exchange account. Prices move; the final amount per coin can differ slightly.</p>
        </div>
      )}
    </Sheet>
  );
}

function AutopilotSheet({ b, onClose }) {
  const qc = useQueryClient();
  const ap = useAutopilotInfo();
  const venues = ap.data?.venues || [];
  const linked = venues.filter((v) => v.linked);
  const freqs = ap.data?.allowed?.frequencies || ["monthly"];
  const [venue, setVenue] = useState(null);
  const [amount, setAmount] = useState(Math.max(b.min_inr || 0, ap.data?.min_inr || 1000, 5000));
  const [sch, setSch] = useState({ frequency: "monthly", weekday: 0, day: 5 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const v = venue || linked[0]?.venue;
  const go = async () => {
    setErr(""); setBusy(true);
    try { await api.post(`/baskets/${b.id}/autopilot`, { venue: v, amount_inr: Number(amount), ...scheduleBody(sch) }); qc.invalidateQueries({ queryKey: ["autopilot"] }); setDone(true); }
    catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <Sheet open onClose={onClose} title={`Autopilot: ${b.name}`}>
      {done ? (
        <div className="space-y-3">
          <p className="text-[16px] font-semibold text-bz-accent">Autopilot on: {inr(amount)} into {b.name}.</p>
          <Link to="/app/autopilot" className="block"><Button className="w-full">See my autopilots</Button></Link>
        </div>
      ) : ap.isLoading ? <p className="text-sm text-bz-muted">Loading your exchanges…</p> : !linked.length ? (
        <div className="space-y-3">
          <p className="text-[15px]">Link your KuCoin or Binance account first (trade-only key).</p>
          <Link to="/app/autopilot" className="block"><Button className="w-full">Link an exchange</Button></Link>
        </div>
      ) : (
        <div className="space-y-4">
          <VenuePicker venues={venues} value={v} onChange={setVenue} />
          <Field label="Amount each time"><MoneyInput value={amount} onChange={setAmount} data-testid="basket-ap-amount" /></Field>
          <ScheduleFields value={sch} onChange={setSch} frequencies={freqs} />
          {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
          <Button className="w-full" onClick={go} loading={busy} disabled={!Number(amount)} data-testid="basket-ap-go">Start the autopilot</Button>
        </div>
      )}
    </Sheet>
  );
}

function BasketCard({ b, onAction }) {
  return (
    <Card data-testid={`basket-${b.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-bzserif text-[22px] font-semibold leading-tight">{b.name}</h3>
          {b.theme && <p className="text-[13px] text-bz-muted mt-0.5">{b.theme}</p>}
        </div>
        {b.min_inr != null && <Chip tone="gold">Min {inr(b.min_inr)}</Chip>}
      </div>
      {b.description && <p className="text-[15px] mt-3">{b.description}</p>}
      <div className="mt-4"><WeightBar items={b.coins} valueKey="weight_pct" /></div>
      {b.risk_note && <p className="text-[13.5px] mt-3 rounded-bzbtn bg-bz-miss-tint px-3 py-2"><b className="text-bz-miss">Risk:</b> {b.risk_note}</p>}
      {b.change_note && <p className="text-[13.5px] mt-2 rounded-bzbtn bg-bz-gold-tint px-3 py-2"><b className="text-bz-gold-deep">Latest change{b.changed_at ? ` (${sdate(b.changed_at)})` : ""}:</b> {b.change_note}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-4">
        <Button variant="quiet" onClick={() => onAction("practice", b)} data-testid={`basket-practice-${b.id}`}>Practice</Button>
        <Button onClick={() => onAction("invest", b)} data-testid={`basket-invest-${b.id}`}>Invest now</Button>
        <Button variant="secondary" onClick={() => onAction("autopilot", b)} data-testid={`basket-autopilot-${b.id}`}>Monthly autopilot</Button>
      </div>
    </Card>
  );
}

export default function Baskets() {
  const can = useFeature("baskets");
  const q = useQuery({ queryKey: ["baskets"], queryFn: async () => (await api.get("/baskets")).data, enabled: can });
  const [act, setAct] = useState(null);
  const header = <PageHeader eyebrow={["Crypto", "_Baskets"]} title="Ready-made" accent="coin groups." sub="Each basket is a small group of coins around one idea, with set weights. Practise it, buy it once, or buy it every month." />;
  return (
    <Gate feature="baskets" header={header}>
      <div className="space-y-4">
        {header}
        <Loadable q={q} what="baskets" lines={5}>
          {(d) => (d.items || []).length ? (
            <div className="grid gap-3 md:grid-cols-2 items-start">{d.items.map((b) => <BasketCard key={b.id} b={b} onAction={(k, x) => setAct({ k, b: x })} />)}</div>
          ) : <Empty icon={Layers} title="Baskets are being prepared" sub="New baskets show up here when they're ready." />}
        </Loadable>
        <Label className="mt-2">Good to know</Label>
        <p className="text-[12px] text-bz-muted">Baskets are model groups for learning, not advice for you. When a basket changes you get a note in your inbox. Crypto is unregulated in India; 30% tax and 1% TDS apply.</p>
        {act?.k === "practice" && <PracticeSheet b={act.b} onClose={() => setAct(null)} />}
        {act?.k === "invest" && <InvestSheet b={act.b} onClose={() => setAct(null)} />}
        {act?.k === "autopilot" && <AutopilotSheet b={act.b} onClose={() => setAct(null)} />}
      </div>
    </Gate>
  );
}
