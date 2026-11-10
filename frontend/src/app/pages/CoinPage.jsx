// /app/coin/:symbol — verdict + history, Forecast (7 / 30 days, low–high band), Bull vs Bear Debate, watch star.
// Adapted from Bullzeye AssetScreen + tools.jsx.
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, apiError } from "@/lib/api";
import { useFeature } from "@/context/AuthContext";
import { track } from "@/lib/attribution";
import { ago, hdate, sdate, usd } from "@/lib/format";
import { AXIS_TICK, C, TOOLTIP } from "../components/chart";
import { Points } from "../components/VerdictCard";
import { Button, Card, Chip, Disclaimer, ErrorCard, Label, Segmented, SkeletonCard, Spinner } from "../components/ui";
import { BackLink, CoinBadge, LockCard, Move, UsageLine, VERDICT_TEXT, VerdictChip, WatchStar, useWatchlist } from "../components/common";

// Shared runner for metered tools: handles 402/403 inline.
function useTool() {
  const [s, setS] = useState({ status: "idle" });
  const run = async (fn) => {
    setS({ status: "loading" });
    try { setS({ status: "done", data: (await fn()) || {} }); }
    catch (e) {
      const st = e?.response?.status;
      const d = e?.response?.data?.detail;
      if ((st === 402 || st === 403) && d) setS({ status: "gate", detail: d });
      else setS({ status: "error", msg: apiError(e) });
    }
  };
  return [s, run];
}

function GateInline({ detail, feature }) {
  return <LockCard feature={detail.feature || feature} planNeeded={detail.plan_needed} kind={detail.code === "limit" ? "limit" : "locked"} used={detail.used} limit={detail.limit} msg={detail.msg} />;
}

function ForecastChart({ f }) {
  const rows = useMemo(() => {
    const out = [{ day: 0, price: f.last_price_usd, band: [f.last_price_usd, f.last_price_usd] }];
    (f.path || []).forEach((p) => out.push({ day: p.day, price: p.price_usd, band: [p.low_usd ?? p.price_usd, p.high_usd ?? p.price_usd] }));
    return out;
  }, [f]);
  if (rows.length < 2) return null;
  const up = Number(f.expected_price_usd ?? rows[rows.length - 1].price) >= Number(f.last_price_usd);
  const col = up ? C.accent : C.miss;
  return (
    <div className="h-56 -mx-2" role="img" aria-label="Forecast path with a low to high range">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <CartesianGrid stroke={C.line} vertical={false} />
          <XAxis dataKey="day" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={(d) => (d === 0 ? "Today" : `Day ${d}`)} interval="preserveStartEnd" minTickGap={28} />
          <YAxis domain={["auto", "auto"]} tick={AXIS_TICK} tickLine={false} axisLine={false} width={64} tickFormatter={(v) => usd(v)} />
          <Tooltip {...TOOLTIP} labelFormatter={(d) => (d === 0 ? "Today" : `Day ${d}`)}
            formatter={(v, n) => (Array.isArray(v) ? [`${usd(v[0])} – ${usd(v[1])}`, "Range"] : [usd(v), "Expected"])} />
          {f.last_price_usd != null && <ReferenceLine y={f.last_price_usd} stroke={C.muted} strokeDasharray="4 4" />}
          <Area dataKey="band" stroke="none" fill={col} fillOpacity={0.14} isAnimationActive={false} />
          <Line dataKey="price" stroke={col} strokeWidth={2.5} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Forecast({ symbol }) {
  const can = useFeature("forecast");
  const [h, setH] = useState(7);
  const [s, run] = useTool();
  const go = () => { track("tool_opened", { tool: "forecast", symbol, horizon: h }); run(async () => (await api.post("/verdicts/forecast", { symbol, horizon_days: h }, { _silentGate: true })).data); };
  const f = s.data;
  return (
    <Card>
      <Label>Price Forecast</Label>
      <p className="text-[15px] text-bz-muted">Where the price could go, with a low–high range. Prices in US dollars; crypto trades 24/7.</p>
      {!can ? <div className="mt-3"><LockCard feature="forecast" /></div> : (
        <>
          <Segmented className="mt-3" options={[{ value: 7, label: "7 days" }, { value: 30, label: "30 days" }]} value={h} onChange={setH} label="Horizon" testid="forecast-horizon" />
          <Button className="w-full mt-2.5" onClick={go} loading={s.status === "loading"} data-testid="forecast-run">Run forecast</Button>
        </>
      )}
      {s.status === "loading" && <Spinner label="Running the forecast model" />}
      {s.status === "error" && <p className="text-sm text-bz-miss mt-2" role="alert">{s.msg}</p>}
      {s.status === "gate" && <div className="mt-3"><GateInline detail={s.detail} feature="forecast" /></div>}
      {s.status === "done" && f && (
        <div className="mt-4 space-y-3 rise-in" data-testid="forecast-result">
          <div>
            <div className="text-[12px] text-bz-muted">Expected in {f.horizon_days || h} days</div>
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-[28px] font-semibold tabular">{usd(f.expected_price_usd)}</span>
              <Move v={f.expected_move_pct} />
            </div>
            <div className="text-[14px] text-bz-muted">Range {usd(f.low_usd)} – {usd(f.high_usd)} · from {usd(f.last_price_usd)} now</div>
          </div>
          <ForecastChart f={f} />
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-bz-muted">
            {f.model && <Chip>{f.model === "kronos" ? "AI model" : "Statistical model"}</Chip>}
            {f.as_of && <span>As of {ago(f.as_of)}</span>}
          </div>
          <UsageLine usage={f.usage} what="forecasts" />
          <Disclaimer text={f.disclaimer} />
        </div>
      )}
    </Card>
  );
}

function Debate({ symbol }) {
  const can = useFeature("debate");
  const [s, run] = useTool();
  const go = () => { track("tool_opened", { tool: "debate", symbol }); run(async () => (await api.post("/verdicts/debate", { symbol }, { _silentGate: true })).data); };
  const d = s.data;
  const side = (title, tone, pts) => (
    <div className="rounded-bzbtn border border-bz-line bg-bz-panel px-3.5 py-3">
      <div className={`text-[14px] font-semibold ${tone}`}>{title}</div>
      {(pts || []).length ? (
        <ul className="mt-2 space-y-2.5">
          {pts.map((p, i) => (
            <li key={i}><p className="text-[15px] font-semibold">{p.point || p}</p>{p.evidence && <p className="text-[13.5px] text-bz-muted mt-0.5">{p.evidence}</p>}</li>
          ))}
        </ul>
      ) : <p className="text-[14px] text-bz-muted mt-2">No points.</p>}
    </div>
  );
  return (
    <Card>
      <Label>Bull vs Bear Debate</Label>
      <p className="text-[15px] text-bz-muted">Two AI analysts argue for and against {symbol}. Then a chair weighs both and makes the call.</p>
      {!can ? <div className="mt-3"><LockCard feature="debate" /></div>
        : <Button className="w-full mt-3" variant={d ? "secondary" : "primary"} onClick={go} loading={s.status === "loading"} data-testid="debate-run">{d ? "Run a fresh debate" : "Start the debate"}</Button>}
      {s.status === "loading" && <Spinner label="The analysts are debating. This can take a minute" />}
      {s.status === "error" && <p className="text-sm text-bz-miss mt-2" role="alert">{s.msg}</p>}
      {s.status === "gate" && <div className="mt-3"><GateInline detail={s.detail} feature="debate" /></div>}
      {s.status === "done" && d && (
        <div className="mt-4 space-y-3 rise-in" data-testid="debate-result">
          {d.made_by === "rules" && <p className="text-[14px] text-bz-muted">The AI analysts weren't available, so this debate comes from our backup rules.</p>}
          <div className="grid gap-2 sm:grid-cols-2">
            {side("The bull case", "text-bz-accent", d.bull)}
            {side("The bear case", "text-bz-miss", d.bear)}
          </div>
          {d.chair && (
            <Card inset>
              <Label className="mb-1.5">The chair's call</Label>
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`font-bzserif text-[26px] font-semibold leading-none ${VERDICT_TEXT[d.chair.verdict] || ""}`}>{d.chair.verdict}</span>
                {d.chair.confidence != null && <span className="text-[14px] text-bz-muted">{d.chair.confidence}% confidence</span>}
              </div>
              {d.chair.call && <p className="text-[15px] mt-2">{d.chair.call}</p>}
            </Card>
          )}
          <UsageLine usage={d.usage} what="debates" />
          <Disclaimer text={d.disclaimer} />
        </div>
      )}
    </Card>
  );
}

export default function CoinPage() {
  const { symbol: raw } = useParams();
  const symbol = String(raw || "").toUpperCase();
  const wl = useWatchlist();
  const details = useFeature("verdict_details");
  const q = useQuery({ queryKey: ["coin", symbol], queryFn: async () => (await api.get(`/verdicts/coin/${encodeURIComponent(symbol)}`)).data });
  const d = q.data || {};
  const v = d.verdict;
  const coin = d.coin || {};
  const name = coin.name || v?.name || symbol;
  const price = coin.price_usd ?? v?.price_usd;
  const change = coin.change_24h ?? v?.change_24h;
  return (
    <div className="space-y-5">
      <BackLink to="/app/verdicts">Verdicts</BackLink>
      <header className="flex items-start gap-3">
        <CoinBadge symbol={symbol} size={48} />
        <div className="min-w-0 flex-1">
          <h1 className="font-bzdisplay text-[31px] sm:text-[39px] font-bold leading-[1.05]">{name}</h1>
          {name !== symbol && <p className="text-[15px] font-semibold text-bz-muted">{symbol}</p>}
          {(price != null || change != null) && <p className="text-[15px] mt-1"><span className="tabular font-semibold">{usd(price)}</span> <Move v={change} className="text-[14px]" /></p>}
        </div>
        <WatchStar symbol={symbol} watched={v?.watched} wl={wl} />
      </header>

      {q.isLoading ? <SkeletonCard lines={4} /> : q.isError ? (
        q.error?.response?.status === 404
          ? <Card inset><p className="text-[15px]">We don't have a verdict for {symbol}. Verdicts cover the top coins by size. Try <Link to="/app/xray" className="font-semibold text-bz-accent">Coin X-Ray</Link> to check any coin.</p></Card>
          : <ErrorCard error={q.error} onRetry={() => q.refetch()} what="this coin" />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] items-start">
          <div className="space-y-5">
            <Card>
              <Label>Today's verdict{v?.date ? `, ${hdate(v.date)}` : ""}</Label>
              {v ? (
                <>
                  <div className="flex items-baseline gap-3 flex-wrap">
                    <span className={`font-bzdisplay text-[44px] leading-none font-bold ${VERDICT_TEXT[v.verdict] || ""}`}>{v.verdict}</span>
                    {v.confidence != null && <span className="text-[15px] text-bz-muted">{v.confidence}% confidence</span>}
                  </div>
                  {v.changed_from && <div className="mt-2"><Chip tone="gold">Changed from {v.changed_from}</Chip></div>}
                  {v.summary && <p className="text-[16px] mt-3">{v.summary}</p>}
                  {details ? <Points bull={v.bull} bear={v.bear} chair={v.chair} />
                    : <p className="text-[14px] text-bz-muted mt-3">The reasons behind the call come with the ₹2,000 plan.</p>}
                </>
              ) : <p className="text-[15px]">The first verdict for {symbol} arrives after the next morning run.</p>}
            </Card>
            {(d.history || []).length > 0 && (
              <Card>
                <Label>Verdict history</Label>
                <ul className="divide-y divide-bz-line">
                  {d.history.slice(0, 30).map((h) => (
                    <li key={h.date} className="flex items-center justify-between gap-3 py-2 text-[14px]">
                      <span className="text-bz-muted">{sdate(h.date)}</span><VerdictChip v={h.verdict} conf={h.confidence} />
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
          <div className="space-y-5">
            <Forecast symbol={symbol} />
            <Debate symbol={symbol} />
          </div>
        </div>
      )}
      <Disclaimer text={d.disclaimer} className="pt-4 border-t border-bz-line" />
    </div>
  );
}
