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
      <div className="text-[14px] text-bz-muted">Market mood</div>
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
          <p className="font-bzdisplay text-[25px] font-bold leading-tight">{cycle.phase || "—"}</p>
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
      <div className="flex justify-between text-[13px] text-bz-muted">
        <span>Halving{cycle.last_halving ? `, ${monthLabel(cycle.last_halving)}` : ""}</span>
        <span>Next{cycle.next_halving_est ? `, ${monthLabel(cycle.next_halving_est)}` : ""}</span>
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
            <span className="text-[14px] font-semibold text-bz-muted">{c.symbol}</span>
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
            <div className="text-[14px] text-bz-muted">Whole crypto market</div>
            <div className="text-[20px] font-semibold tabular mt-1">{usdShort(p.total_mcap_usd)}</div>
            {p.btc_dominance_pct != null && <div className="text-[12px] text-bz-muted">Bitcoin is {Number(p.btc_dominance_pct).toFixed(1)}% of it</div>}
          </div>
        )}
        {etf && etf.net_usd_m != null && !compact && (
          <div className="rounded-bzbtn border border-bz-line bg-bz-card px-3.5 py-3">
            <div className="text-[14px] text-bz-muted">Money into Bitcoin ETFs{etf.date ? `, ${sdate(etf.date)}` : ""}</div>
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

// ---- Market strip (Today) ------------------------------------------------------------------------------
// One surface split by hairlines instead of a card per number: coins on top (rupees first, dollars under),
// the market's mood and size below. Direction is shown with ▲/▼ as well as colour.
const COIN_NAME = { BTC: "Bitcoin", ETH: "Ethereum", SOL: "Solana", XRP: "XRP", BNB: "BNB", DOGE: "Dogecoin" };

function Change({ v }) {
  if (v == null || Number.isNaN(Number(v))) return <span className="text-bz-muted">—</span>;
  const n = Number(v);
  const cls = n > 0 ? "text-bz-accent" : n < 0 ? "text-bz-miss" : "text-bz-muted";
  return (
    <span className={`text-[14px] font-semibold tabular ${cls}`}>
      <span aria-hidden>{n > 0 ? "▲ " : n < 0 ? "▼ " : ""}</span>{pct(n)}<span className="sr-only"> in 24 hours</span>
    </span>
  );
}

function Mood({ fg }) {
  if (!fg || fg.value == null) return null;
  const v = Math.max(0, Math.min(100, Number(fg.value)));
  return (
    <div className="min-w-0" data-testid="fear-greed">
      <p className="text-[14px] text-bz-muted">Market mood</p>
      <p className="mt-0.5"><span className={`font-bzdisplay text-[25px] font-bold tabular leading-none ${fgTone(v)}`}>{v}</span>
        <span className="text-[15px] font-semibold ml-2">{fg.label}</span></p>
      <div className="relative h-1.5 rounded-full mt-3 bg-bz-inset" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded-full bg-bz-gold" style={{ width: `${v}%` }} />
      </div>
      <p className="flex justify-between text-[12px] text-bz-muted mt-1"><span>Fear</span><span>Greed</span></p>
    </div>
  );
}

export function MarketStrip({ pulse: p }) {
  if (!p) return null;
  const coins = (p.coins || []).slice(0, 4);
  const etf = p.etf_flows;
  return (
    <section className="rounded-bzcard bg-bz-card border border-bz-line" aria-labelledby="market-title" data-testid="market-pulse">
      <div className="flex items-baseline justify-between gap-3 px-5 pt-4">
        <h2 id="market-title" className="font-bzdisplay text-[20px] font-bold">Market today</h2>
        {p.as_of && <p className="text-[13px] text-bz-muted">Updated {ago(p.as_of)}</p>}
      </div>
      <ul className="grid grid-cols-2 md:grid-cols-4 mt-2">
        {coins.map((c, i) => (
          <li key={c.symbol} data-testid={`price-${c.symbol}`}
            className={`px-5 py-3.5 min-w-0 border-bz-line ${i % 2 ? "border-l" : ""} ${i > 1 ? "border-t md:border-t-0" : ""} ${i === 2 ? "md:border-l" : ""}`}>
            <p className="text-[14px] text-bz-muted truncate">{COIN_NAME[c.symbol] || c.symbol}</p>
            <p className="font-bzdisplay text-[25px] font-bold tabular leading-tight truncate" title={c.price_inr != null ? inr(c.price_inr) : undefined}>
              {c.price_inr != null ? (Number(c.price_inr) >= 1e5 ? inrShort(c.price_inr) : inr(c.price_inr)) : usd(c.price_usd)}
            </p>
            <p className="flex items-baseline gap-2 flex-wrap"><Change v={c.change_24h} />{c.price_inr != null && <span className="text-[13px] text-bz-muted tabular">{usd(c.price_usd)}</span>}</p>
          </li>
        ))}
      </ul>
      <div className="grid grid-cols-1 sm:grid-cols-3 border-t border-bz-line">
        <div className="px-5 py-4"><Mood fg={p.fear_greed} /></div>
        {(p.total_mcap_usd != null || p.btc_dominance_pct != null) && (
          <div className="px-5 py-4 border-t sm:border-t-0 sm:border-l border-bz-line min-w-0">
            <p className="text-[14px] text-bz-muted">Whole crypto market</p>
            <p className="font-bzdisplay text-[25px] font-bold tabular leading-tight mt-0.5">{usdShort(p.total_mcap_usd)}</p>
            {p.btc_dominance_pct != null && <p className="text-[13px] text-bz-muted">Bitcoin is {Number(p.btc_dominance_pct).toFixed(1)}% of it</p>}
          </div>
        )}
        {etf && etf.net_usd_m != null && (
          <div className="px-5 py-4 border-t sm:border-t-0 sm:border-l border-bz-line min-w-0">
            <p className="text-[14px] text-bz-muted">Money into Bitcoin ETFs{etf.date ? `, ${sdate(etf.date)}` : ""}</p>
            <p className={`font-bzdisplay text-[25px] font-bold tabular leading-tight mt-0.5 ${etf.net_usd_m >= 0 ? "text-bz-accent" : "text-bz-miss"}`}>
              {etf.net_usd_m >= 0 ? "+" : "−"}${Math.abs(etf.net_usd_m).toLocaleString("en-US")}M
            </p>
            <p className="text-[13px] text-bz-muted truncate">{etf.note || (etf.net_usd_m >= 0 ? "More money went in than came out" : "More money came out than went in")}</p>
          </div>
        )}
      </div>
    </section>
  );
}
