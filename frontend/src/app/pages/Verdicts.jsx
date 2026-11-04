// /app/verdicts — today's verdicts, Market Pulse, Monday Picks.
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Scale } from "lucide-react";
import { api } from "@/lib/api";
import { useFeature } from "@/context/AuthContext";
import { ago, hdate, usd } from "@/lib/format";
import PulseStrip from "../components/Pulse";
import VerdictCard from "../components/VerdictCard";
import { Card, Disclaimer, Empty, Label, Loadable, PageHeader } from "../components/ui";
import { Gate, LockCard, Move, VerdictChip, useWatchlist } from "../components/common";

function MondayPicks() {
  const can = useFeature("monday_picks");
  const q = useQuery({ queryKey: ["picks"], queryFn: async () => (await api.get("/picks/monday", { _silentGate: true })).data, enabled: can });
  if (!can) return <LockCard feature="monday_picks" />;
  return (
    <Loadable q={q} what="Monday Picks">
      {(d) => !d.published || !(d.picks || []).length ? (
        <Empty title="This week's picks are coming" sub="Two coins are picked every Monday morning, with the reasoning in plain words." />
      ) : (
        <div className="space-y-3">
          {d.week_of && <p className="text-[13px] text-bz-muted">Week of {hdate(d.week_of)}</p>}
          <div className="grid gap-3 sm:grid-cols-2">
            {d.picks.map((p) => (
              <Card key={p.symbol} data-testid={`pick-${p.symbol}`}>
                <div className="flex items-start justify-between gap-2">
                  <Link to={`/app/coin/${p.symbol}`} className="min-w-0">
                    <span className="block text-[18px] font-semibold">{p.name || p.symbol}</span>
                    <span className="font-bzmono text-[11px] uppercase tracking-[0.14em] text-bz-muted">{p.symbol}</span>
                  </Link>
                  <VerdictChip v={p.verdict} conf={p.confidence} />
                </div>
                {p.reasoning && <p className="text-[15px] mt-3">{p.reasoning}</p>}
                <div className="mt-3 pt-3 border-t border-bz-line text-[13px] flex flex-wrap gap-x-3 gap-y-1">
                  <span className="text-bz-muted">Picked at <b className="text-bz-ink tabular">{usd(p.price_at_pick_usd)}</b></span>
                  <span className="text-bz-muted">Now <b className="text-bz-ink tabular">{usd(p.price_now_usd)}</b></span>
                  <Move v={p.change_pct} />
                </div>
              </Card>
            ))}
          </div>
          <Disclaimer text={d.disclaimer} />
        </div>
      )}
    </Loadable>
  );
}

export default function Verdicts() {
  const details = useFeature("verdict_details");
  const wl = useWatchlist();
  const q = useQuery({ queryKey: ["verdicts-today"], queryFn: async () => (await api.get("/verdicts/today")).data });
  const header = <PageHeader eyebrow={["Crypto", "_Verdicts"]} title="Today's call on" accent="the top coins." sub="Every morning our AI committee looks at each coin and says Bullish, Neutral or Bearish, with how sure it is." />;
  return (
    <Gate feature="verdicts" header={header}>
      <div className="space-y-6">
        {header}
        <section className="space-y-3">
          <Loadable q={q} what="today's verdicts" lines={6}>
            {(d) => (
              <>
                {(d.date || d.updated_at) && <p className="text-[13px] text-bz-muted">{d.date ? hdate(d.date) : ""}{d.updated_at ? ` · updated ${ago(d.updated_at)}` : ""}</p>}
                {!(d.coins || []).length ? (
                  <Empty icon={Scale} title="Today's verdicts are on their way" sub="They are ready every morning by 6 am. Check back soon." />
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {d.coins.map((v) => <VerdictCard key={v.symbol} v={v} wl={wl} details={details} />)}
                  </div>
                )}
                {!details && (d.coins || []).length > 0 && (
                  <Card inset><p className="text-[14.5px]">Want the reasons behind each call? Bull points, bear points and the chair's call come with the <Link to="/app/plans?plan=lite&from=verdict_details" className="font-semibold text-bz-accent">₹2,000 plan</Link>.</p></Card>
                )}
                <Disclaimer text={d.disclaimer} />
              </>
            )}
          </Loadable>
        </section>
        <section>
          <Label>Market Pulse</Label>
          <PulseStrip />
        </section>
        <section>
          <Label>Monday Picks</Label>
          <MondayPicks />
        </section>
      </div>
    </Gate>
  );
}
