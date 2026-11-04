// Market Pulse strip: BTC / ETH / SOL prices, Fear & Greed, Bitcoin Cycle Meter (+ ETF flows, mcap when present).
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useFeature } from "@/context/AuthContext";
import { ago, inr, inrShort, monthLabel, pct, sdate, usd, usdShort } from "@/lib/format";
import { Card, ErrorCard, Label, Skeleton } from "./ui";
import { Move } from "./common";

// Logged-in users with `pulse` get /pulse (richer); everyone else /public/pulse.
export function usePulse() {
  const full = useFeature("pulse");
  return useQuery({
    queryKey: ["pulse", full ? "full" : "public"],
    queryFn: async () => (await api.get(full ? "/pulse" : "/public/pulse", { _silentGate: true })).data,
    staleTime: 5 * 60_000,
  });
}

function fgTone(v) {
  if (v == null) return "text-bz-muted";
  if (v < 25) return "text-bz-miss";
  if (v < 45) return "text-bz-gold-deep";
  if (v <= 55) return "text-bz-muted";
  return "text-bz-accent";
}

export function FearGreed({ fg }) {
  if (!fg || fg.value == null) return null;
  const v = Math.max(0, Math.min(100, Number(fg.value)));
  return (
    <div className="rounded-bzbtn border border-bz-line bg-bz-card px-3.5 py-3" data-testid="fear-greed">
      <div className="font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-muted">Fear &amp; Greed</div>
      <div className="flex items-baseline gap-2 mt-1">
        <span className={`text-[22px] font-semibold tabular ${fgTone(v)}`}>{v}</span>
        <span className="text-[13px] font-semibold">{fg.label}</span>
      </div>
      <div className="relative h-2 rounded-full mt-2" style={{ background: "linear-gradient(90deg, var(--bz-miss), var(--bz-gold) 50%, var(--bz-accent))" }} aria-hidden>
        <span className="absolute -top-1 w-1.5 h-4 rounded-full bg-bz-ink border-2 border-bz-card" style={{ left: `calc(${v}% - 3px)` }} />
      </div>
      <div className="flex justify-between text-[10.5px] text-bz-muted mt-1"><span>Fear</span><span>Greed</span></div>
    </div>
  );
}

export function CycleMeter({ cycle }) {
  if (!cycle) return null;
  const pos = Math.max(0, Math.min(100, Number(cycle.position_pct) || 0));
  return (
    <Card data-testid="cycle-meter">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <Label className="mb-1">Bitcoin Cycle Meter</Label>
          <p className="font-bzserif text-[24px] font-semibold leading-tight">{cycle.phase || "—"} <span className="text-bz-gold">phase</span></p>
        </div>
        <div className="text-right text-[13px] text-bz-muted">
          {cycle.days_since != null && <div><b className="text-bz-ink tabular">{Number(cycle.days_since).toLocaleString("en-IN")}</b> days since halving</div>}
          {cycle.days_to_next != null && <div><b className="text-bz-ink tabular">{Number(cycle.days_to_next).toLocaleString("en-IN")}</b> days to the next</div>}
        </div>
      </div>
      <div className="relative mt-5 mb-2">
        <div className="h-3 rounded-full overflow-hidden flex" aria-hidden>
          <div className="h-full flex-1 bg-bz-accent-tint" />
          <div className="h-full flex-1 bg-bz-accent" style={{ opacity: 0.55 }} />
          <div className="h-full flex-1 bg-bz-gold" style={{ opacity: 0.6 }} />
          <div className="h-full flex-1 bg-bz-miss-tint" />
        </div>
        <div className="absolute -top-2 flex flex-col items-center" style={{ left: `calc(${pos}% - 10px)` }}
          role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pos} aria-label="Position in the 4-year Bitcoin cycle">
          <span className="w-5 h-7 rounded-md bg-bz-ink border-[3px] border-bz-card shadow" />
        </div>
      </div>
      <div className="flex justify-between font-bzmono text-[10.5px] uppercase tracking-[0.1em] text-bz-muted">
        <span>Halving{cycle.last_halving ? ` · ${monthLabel(cycle.last_halving)}` : ""}</span>
        <span>Next{cycle.next_halving_est ? ` · ${monthLabel(cycle.next_halving_est)}` : ""}</span>
      </div>
      {cycle.phase_note && <p className="text-[15px] mt-3">{cycle.phase_note}</p>}
      {(cycle.ath_usd != null || cycle.drawdown_from_ath_pct != null) && (
        <p className="text-[13px] text-bz-muted mt-2">
          {cycle.ath_usd != null && <>All-time high {usd(cycle.ath_usd)}</>}
          {cycle.drawdown_from_ath_pct != null && <> · now {pct(-Math.abs(cycle.drawdown_from_ath_pct), 1, false)} from it</>}
        </p>
      )}
    </Card>
  );
}

export function PriceTiles({ coins = [] }) {
  const list = (coins || []).slice(0, 3);
  if (!list.length) return null;
  return (
    <div className="grid grid-cols-3 gap-2">
      {list.map((c) => (
        <div key={c.symbol} className="rounded-bzbtn border border-bz-line bg-bz-card px-3 py-3 min-w-0" data-testid={`price-${c.symbol}`}>
          <div className="flex items-center justify-between gap-1">
            <span className="font-bzmono text-[11px] uppercase tracking-[0.14em] text-bz-muted">{c.symbol}</span>
            <Move v={c.change_24h} className="text-[12px]" />
          </div>
          <div className="text-[16px] sm:text-[18px] font-semibold tabular mt-1 truncate" title={c.price_inr != null ? inr(c.price_inr) : undefined}>{c.price_inr != null ? (Number(c.price_inr) >= 1e5 ? inrShort(c.price_inr) : inr(c.price_inr)) : usd(c.price_usd)}</div>
          {c.price_inr != null && c.price_usd != null && <div className="text-[12px] text-bz-muted tabular truncate">{usd(c.price_usd)}</div>}
        </div>
      ))}
    </div>
  );
}

// Full strip: prices + F&G (+ extras) + cycle meter.
export default function PulseStrip({ showCycle = true, compact = false }) {
  const q = usePulse();
  if (q.isLoading) return <Card><Skeleton lines={3} /></Card>;
  if (q.isError) return <ErrorCard error={q.error} onRetry={() => q.refetch()} what="market prices" />;
  const p = q.data || {};
  const etf = p.etf_flows;
  return (
    <div className="space-y-3" data-testid="market-pulse">
      <PriceTiles coins={p.coins} />
      <div className={`grid gap-2 ${compact ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1 sm:grid-cols-3"}`}>
        <FearGreed fg={p.fear_greed} />
        {(p.total_mcap_usd != null || p.btc_dominance_pct != null) && (
          <div className="rounded-bzbtn border border-bz-line bg-bz-card px-3.5 py-3">
            <div className="font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-muted">Whole market</div>
            <div className="text-[20px] font-semibold tabular mt-1">{usdShort(p.total_mcap_usd)}</div>
            {p.btc_dominance_pct != null && <div className="text-[12px] text-bz-muted">Bitcoin is {Number(p.btc_dominance_pct).toFixed(1)}% of it</div>}
          </div>
        )}
        {etf && etf.net_usd_m != null && !compact && (
          <div className="rounded-bzbtn border border-bz-line bg-bz-card px-3.5 py-3">
            <div className="font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-muted">Bitcoin ETF flows{etf.date ? ` · ${sdate(etf.date)}` : ""}</div>
            <div className={`text-[20px] font-semibold tabular mt-1 ${etf.net_usd_m >= 0 ? "text-bz-accent" : "text-bz-miss"}`}>{etf.net_usd_m >= 0 ? "+" : "−"}${Math.abs(etf.net_usd_m).toLocaleString("en-US")}M</div>
            {etf.note && <div className="text-[12px] text-bz-muted truncate">{etf.note}</div>}
          </div>
        )}
      </div>
      {showCycle && <CycleMeter cycle={p.cycle} />}
      {p.as_of && <p className="text-[12px] text-bz-muted">Prices as of {ago(p.as_of)}.</p>}
    </div>
  );
}
