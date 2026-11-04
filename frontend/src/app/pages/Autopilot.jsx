// /app/autopilot — SIP Autopilot: link KuCoin / Binance (trade-only key), USDT balance, create and manage auto-buys.
// Patterns from Bullzeye CryptoDca.jsx + Earn.jsx (LinkExchangeSheet, DcaCard).
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Repeat, ShieldCheck } from "lucide-react";
import { useFeature } from "@/context/AuthContext";
import { api, apiError } from "@/lib/api";
import { inr, venueName } from "@/lib/format";
import { Button, Card, Chip, Empty, Field, Input, Label, Loadable, MoneyInput, PageHeader, Segmented, Sheet } from "../components/ui";
import { Gate } from "../components/common";
import { DcaPlanCard, ScheduleFields, scheduleBody, VenuePicker } from "../components/Dca";

const VENUES = ["kucoin", "binance"];

function LinkSheet({ open, onClose, initialVenue }) {
  const qc = useQueryClient();
  const [venue, setVenue] = useState(initialVenue || "kucoin");
  const [f, setF] = useState({ api_key: "", api_secret: "", passphrase: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { if (open) { setVenue(initialVenue || "kucoin"); setF({ api_key: "", api_secret: "", passphrase: "" }); setErr(""); } }, [open, initialVenue]);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const body = { venue, api_key: f.api_key.trim(), api_secret: f.api_secret.trim() };
      if (venue === "kucoin") body.passphrase = f.passphrase;
      const { data } = await api.post("/autopilot/link", body);
      qc.invalidateQueries({ queryKey: ["autopilot"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      if (data && data.linked === false) setErr(data.reason || "The key could not be linked.");
      else onClose();
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  const name = venueName(venue);
  return (
    <Sheet open={open} onClose={onClose} title="Link your exchange">
      <form onSubmit={submit} className="space-y-4">
        <Segmented options={VENUES.map((v) => ({ value: v, label: venueName(v) }))} value={venue} onChange={setVenue} label="Exchange" testid="link-venue" />
        <div className="rounded-bzbtn border border-bz-accent bg-bz-accent-tint px-3.5 py-3 flex gap-2.5">
          <ShieldCheck className="w-5 h-5 text-bz-accent shrink-0 mt-0.5" aria-hidden />
          <p className="text-[14px]"><b>Trading ON, Withdrawals OFF.</b> We refuse keys that can withdraw. Your coins stay in your own {name} account; we can only place buys.</p>
        </div>
        <ol className="text-[14px] space-y-1.5 list-decimal pl-5">
          <li>Open {name} → <b>API Management</b> → Create API.</li>
          <li>Turn on <b>{venue === "kucoin" ? "General + Spot trading" : "Reading + Spot trading"}</b>. Leave <b>Withdrawals off</b>.</li>
          {venue === "kucoin" && <li>Set an API passphrase and note it down.</li>}
          <li>Paste the details below.</li>
        </ol>
        <Field label="API key"><Input value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} autoComplete="off" spellCheck={false} data-testid="link-key" /></Field>
        <Field label="Secret key"><Input type="password" value={f.api_secret} onChange={(e) => setF({ ...f, api_secret: e.target.value })} autoComplete="off" data-testid="link-secret" /></Field>
        {venue === "kucoin" && (
          <Field label="API passphrase"><Input type="password" value={f.passphrase} onChange={(e) => setF({ ...f, passphrase: e.target.value })} autoComplete="off" data-testid="link-passphrase" /></Field>
        )}
        {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
        <Button type="submit" className="w-full" loading={busy} disabled={!f.api_key || !f.api_secret || (venue === "kucoin" && !f.passphrase)} data-testid="link-submit">Check and link</Button>
        <p className="text-[12px] text-bz-muted">Your key is stored encrypted and never shown again.</p>
      </form>
    </Sheet>
  );
}

function Balance({ venue }) {
  const q = useQuery({ queryKey: ["autopilot-balance", venue], queryFn: async () => (await api.get(`/autopilot/balance/${venue}`, { _silentGate: true })).data, staleTime: 60_000 });
  if (q.isLoading) return <span className="text-[13px] text-bz-muted">Checking balance…</span>;
  if (q.isError || !q.data) return <span className="text-[13px] text-bz-muted">Balance not available</span>;
  return <span className="text-[13px]"><b className="tabular">{Number(q.data.usdt || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })} USDT</b> <span className="text-bz-muted">≈ {inr(q.data.inr_est)}</span></span>;
}

function VenueRow({ v, onLink }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const unlink = async () => {
    if (!window.confirm(`Unlink ${venueName(v.venue)}? Autopilots on it will stop.`)) return;
    setBusy(true);
    try { await api.delete(`/autopilot/link/${v.venue}`); qc.invalidateQueries({ queryKey: ["autopilot"] }); qc.invalidateQueries({ queryKey: ["portfolio"] }); }
    finally { setBusy(false); }
  };
  const ok = v.linked && (v.status === "active" || v.status === "ok" || !v.status);
  return (
    <li className="py-3 flex items-start justify-between gap-3" data-testid={`venue-${v.venue}`}>
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[16px] font-semibold">{venueName(v.venue)}</span>
          {v.linked ? <Chip tone={ok ? "bull" : "bear"}>{ok ? "Linked" : v.status || "Problem"}</Chip> : <Chip>Not linked</Chip>}
          {v.key_tail && <span className="font-bzmono text-[12px] text-bz-muted">key …{v.key_tail}</span>}
        </div>
        {v.reason && <p className="text-[13px] text-bz-miss mt-1">{v.reason}</p>}
        {v.linked && <div className="mt-1"><Balance venue={v.venue} /></div>}
      </div>
      {v.linked ? <Button variant="small" onClick={unlink} loading={busy} data-testid={`unlink-${v.venue}`}>Unlink</Button>
        : <Button variant="small" onClick={() => onLink(v.venue)} data-testid={`link-${v.venue}`}>Link</Button>}
    </li>
  );
}

function NewPlan({ d }) {
  const qc = useQueryClient();
  const coins = d.allowed?.coins?.length ? d.allowed.coins : ["BTC"];
  const freqs = d.allowed?.frequencies?.length ? d.allowed.frequencies : ["monthly"];
  const min = d.min_inr || 1000;
  const linked = (d.venues || []).filter((v) => v.linked);
  const [venue, setVenue] = useState(linked[0]?.venue || "kucoin");
  const [coin, setCoin] = useState(coins[0]);
  const [amount, setAmount] = useState(Math.max(min, 2000));
  const [sch, setSch] = useState({ frequency: freqs.includes("monthly") ? "monthly" : freqs[0], weekday: 0, day: 5 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  useEffect(() => { if (linked[0] && !linked.find((v) => v.venue === venue)) setVenue(linked[0].venue); }, [linked, venue]);
  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setOk("");
    if (Number(amount) < min) { setErr(`The smallest amount is ${inr(min)}.`); return; }
    setBusy(true);
    try {
      await api.post("/autopilot/plan", { venue, coin, amount_inr: Number(amount), ...scheduleBody(sch) });
      qc.invalidateQueries({ queryKey: ["autopilot"] });
      setOk(`Autopilot on: ${inr(amount)} into ${coin}.`);
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="space-y-4" data-testid="dca-new">
      <VenuePicker venues={d.venues} value={venue} onChange={setVenue} />
      <Field label="Coin" hint={coins.length === 1 ? "More coins (ETH, SOL, XRP) and weekly buys come with the ₹5,000 plan." : null}>
        <Segmented options={coins} value={coin} onChange={setCoin} label="Coin" testid="dca-coin" />
      </Field>
      <Field label="Amount each time" hint={`At least ${inr(min)}. Converted to USDT at the day's rate.`}>
        <MoneyInput value={amount} onChange={setAmount} min={min} data-testid="dca-amount" />
      </Field>
      <ScheduleFields value={sch} onChange={setSch} frequencies={freqs} />
      {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
      {ok && <p className="text-sm text-bz-accent font-semibold" role="status">{ok}</p>}
      <Button type="submit" className="w-full" loading={busy} disabled={!linked.length} data-testid="dca-create">Start my autopilot</Button>
    </form>
  );
}

export default function Autopilot() {
  const can = useFeature("autopilot");
  const q = useQuery({ queryKey: ["autopilot"], queryFn: async () => (await api.get("/autopilot")).data, enabled: can });
  const [link, setLink] = useState(null);
  const header = <PageHeader eyebrow={["SIP", "_Autopilot"]} title="Buy a little," accent="every month." sub="Set an amount once. We buy for you from your own exchange account, on the day you pick. No timing the market." />;
  return (
    <Gate feature="autopilot" header={header}>
      <div className="space-y-5">
        {header}
        <Loadable q={q} what="your autopilot" lines={5}>
          {(d) => {
            const venues = (d.venues || []).length ? d.venues : VENUES.map((v) => ({ venue: v, linked: false }));
            const anyLinked = venues.some((v) => v.linked);
            const plans = d.plans || [];
            const invested = plans.reduce((s, p) => s + (Number(p.invested_inr) || 0), 0);
            const value = plans.reduce((s, p) => s + (Number(p.value_inr) || 0), 0);
            return (
              <>
                <Card>
                  <Label>Your exchanges</Label>
                  <ul className="divide-y divide-bz-line">{venues.map((v) => <VenueRow key={v.venue} v={v} onLink={setLink} />)}</ul>
                  {!anyLinked && <Button className="w-full mt-3" onClick={() => setLink("kucoin")} data-testid="link-open">Link an exchange</Button>}
                </Card>
                {d.enabled === false && <Card inset><p className="text-[14px]">Autopilot buys are paused for maintenance. Your plans are safe and will resume.</p></Card>}
                {plans.length > 0 && (
                  <Card>
                    <Label>All autopilots</Label>
                    <div className="grid grid-cols-3 gap-2 mb-4">
                      <div className="rounded-bzbtn bg-bz-inset px-3 py-2.5"><div className="text-[11px] text-bz-muted font-bzmono uppercase tracking-[0.12em]">Put in</div><div className="font-semibold tabular">{inr(invested)}</div></div>
                      <div className="rounded-bzbtn bg-bz-inset px-3 py-2.5"><div className="text-[11px] text-bz-muted font-bzmono uppercase tracking-[0.12em]">Worth</div><div className="font-semibold tabular">{inr(value)}</div></div>
                      <div className="rounded-bzbtn bg-bz-inset px-3 py-2.5"><div className="text-[11px] text-bz-muted font-bzmono uppercase tracking-[0.12em]">Return</div><div className={`font-semibold tabular ${value >= invested ? "text-bz-accent" : "text-bz-miss"}`}>{invested ? `${value >= invested ? "+" : ""}${(((value - invested) / invested) * 100).toFixed(1)}%` : "—"}</div></div>
                    </div>
                    <div className="space-y-3">{plans.map((p) => <DcaPlanCard key={p.id} p={p} />)}</div>
                  </Card>
                )}
                <Card>
                  <Label>{plans.length ? "Add another autopilot" : "Start an autopilot"}</Label>
                  {anyLinked ? <NewPlan d={{ ...d, venues }} /> : (
                    <Empty icon={Repeat} title="Link an exchange to start" sub="You need a KuCoin or Binance account with some USDT in it. We buy from there; your coins stay with you." />
                  )}
                </Card>
                <p className="text-[12px] text-bz-muted">Buys run at about 10 am IST. Keep enough USDT in your exchange; if it's short we skip that buy and tell you in your inbox. Crypto is unregulated in India and volatile; 30% tax and 1% TDS apply.</p>
              </>
            );
          }}
        </Loadable>
        <LinkSheet open={!!link} initialVenue={link} onClose={() => setLink(null)} />
      </div>
    </Gate>
  );
}
