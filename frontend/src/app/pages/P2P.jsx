// /app/p2p — P2P Rate Finder: amount → best USDT price per venue + offers (merchant, price, limits, completion, orders, safety), tips.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, Lightbulb } from "lucide-react";
import { useFeature } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { ago, inr, venueName } from "@/lib/format";
import { Button, Card, Chip, Empty, Field, Label, Loadable, MoneyInput, PageHeader } from "../components/ui";
import { Gate } from "../components/common";

const SAFETY = { high: { label: "Safer", tone: "bull" }, medium: { label: "Okay", tone: "gold" }, low: { label: "Careful", tone: "bear" } };
const price = (v) => (v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

function Venue({ v, amount }) {
  const offers = v.offers || [];
  return (
    <Card data-testid={`p2p-${v.venue}`}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[18px] font-semibold">{venueName(v.venue)}</h3>
        <div className="text-right"><div className="text-[11px] text-bz-muted font-bzmono uppercase tracking-[0.12em]">Best price</div><div className="text-[22px] font-semibold tabular text-bz-accent">{price(v.best_price)}</div></div>
      </div>
      {v.best_price && amount ? <p className="text-[13px] text-bz-muted">{inr(amount)} gets about <b className="text-bz-ink tabular">{(amount / v.best_price).toLocaleString("en-IN", { maximumFractionDigits: 2 })} USDT</b></p> : null}
      {offers.length === 0 ? <p className="text-[14px] text-bz-muted mt-3">No offers for this amount right now.</p> : (
        <div className="overflow-x-auto -mx-5 px-5 mt-3">
          <table className="w-full text-[13.5px] min-w-[560px]">
            <thead><tr className="text-left text-bz-muted font-bzmono text-[10.5px] uppercase tracking-[0.1em]">
              <th className="py-2 pr-2 font-medium">Seller</th><th className="py-2 px-2 font-medium text-right">Price</th><th className="py-2 px-2 font-medium">Limits</th>
              <th className="py-2 px-2 font-medium text-right">Done</th><th className="py-2 px-2 font-medium text-right">Orders</th><th className="py-2 pl-2 font-medium">Safety</th></tr></thead>
            <tbody>
              {offers.map((o, i) => {
                const s = SAFETY[o.safety] || { label: o.safety || "—", tone: "muted" };
                return (
                  <tr key={`${o.merchant}-${i}`} className="border-t border-bz-line align-top">
                    <td className="py-2.5 pr-2"><span className="font-semibold">{o.merchant}</span>{(o.payment || []).length > 0 && <span className="block text-[11.5px] text-bz-muted">{o.payment.join(" · ")}</span>}</td>
                    <td className="py-2.5 px-2 text-right tabular font-semibold">{price(o.price)}</td>
                    <td className="py-2.5 px-2 tabular whitespace-nowrap">{inr(o.min_inr)} – {inr(o.max_inr)}</td>
                    <td className="py-2.5 px-2 text-right tabular">{o.completion_pct != null ? `${Number(o.completion_pct).toFixed(1)}%` : "—"}</td>
                    <td className="py-2.5 px-2 text-right tabular">{o.orders != null ? Number(o.orders).toLocaleString("en-IN") : "—"}</td>
                    <td className="py-2.5 pl-2"><Chip tone={s.tone}>{s.label}</Chip></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export default function P2P() {
  const [draft, setDraft] = useState(5000);
  const [amount, setAmount] = useState(5000);
  const [bad, setBad] = useState("");
  const can = useFeature("p2p");
  const q = useQuery({ queryKey: ["p2p", amount], queryFn: async () => (await api.get("/p2p", { params: { amount_inr: amount } })).data, staleTime: 2 * 60_000, enabled: can });
  const header = <PageHeader eyebrow={["P2P", "_Rate finder"]} title="Rupees to USDT," accent="at a fair rate." sub="Compare live P2P offers on Binance and KuCoin for your amount. Safer sellers are marked." />;
  return (
    <Gate feature="p2p" header={header}>
      <div className="space-y-4">
        {header}
        <Card>
          <form noValidate onSubmit={(e) => {
            e.preventDefault();
            const n = Number(draft);
            if (!n || n < 100 || n > 10000000) { setBad("Enter an amount between ₹100 and ₹1,00,00,000."); return; }
            setBad(""); setAmount(n);
          }} className="flex flex-col sm:flex-row gap-2 sm:items-end">
            <Field label="I want to spend" className="flex-1"><MoneyInput value={draft} onChange={setDraft} data-testid="p2p-amount" /></Field>
            <Button type="submit" data-testid="p2p-submit" loading={q.isFetching}>Find rates</Button>
          </form>
          {bad && <p className="text-sm text-bz-miss mt-2" role="alert">{bad}</p>}
        </Card>
        <Loadable q={q} what="P2P rates" lines={6}>
          {(d) => (
            <>
              {d.as_of && <p className="text-[13px] text-bz-muted">{d.asset || "USDT"} / {d.fiat || "INR"} · updated {ago(d.as_of)}</p>}
              {(d.venues || []).length ? <div className="space-y-3">{d.venues.map((v) => <Venue key={v.venue} v={v} amount={amount} />)}</div>
                : <Empty icon={ArrowLeftRight} title="No offers found" sub="Try a different amount, or check again in a few minutes." />}
              {(d.tips || []).length > 0 && (
                <Card inset>
                  <Label className="flex items-center gap-1.5"><Lightbulb className="w-3.5 h-3.5" aria-hidden /> Stay safe on P2P</Label>
                  <ul className="space-y-1.5 text-[14.5px] list-disc pl-5">{d.tips.map((t, i) => <li key={i}>{t}</li>)}</ul>
                </Card>
              )}
            </>
          )}
        </Loadable>
      </div>
    </Gate>
  );
}
