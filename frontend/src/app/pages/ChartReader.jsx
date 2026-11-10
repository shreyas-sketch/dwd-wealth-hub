// /app/chart — Chart Reader: upload a screenshot (multipart `file`) → trend, summary, levels, RSI, patterns, what to watch.
// Adapted from Bullzeye BullBear.jsx chart upload.
import { useEffect, useRef, useState } from "react";
import { ImagePlus, TrendingDown, TrendingUp, MoveRight } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { track } from "@/lib/attribution";
import { Button, Card, Chip, Disclaimer, Field, Input, Label, PageHeader, Spinner } from "../components/ui";
import { Gate, LockCard, UsageLine } from "../components/common";

const TREND = {
  up: { label: "Uptrend", tone: "bull", icon: TrendingUp, cls: "text-bz-accent" },
  down: { label: "Downtrend", tone: "bear", icon: TrendingDown, cls: "text-bz-miss" },
  sideways: { label: "Sideways", tone: "gold", icon: MoveRight, cls: "text-bz-gold-deep" },
};
const MAX_MB = 5;          // same as the server (features/chart_vision.py MAX_BYTES)
const AUTO_RETRIES = 2;   // 503 "busy": the use was refunded, so retrying costs the member nothing
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function List({ items, tone }) {
  if (!items?.length) return <p className="text-[14px] text-bz-muted">None seen.</p>;
  return <ul className={`space-y-1.5 text-[15px] ${tone || ""}`}>{items.map((x, i) => <li key={i} className="tabular">{x}</li>)}</ul>;
}

function ChartResult({ r }) {
  const t = TREND[r.trend] || TREND.sideways;
  const Icon = t.icon;
  return (
    <div className="space-y-3 rise-in" data-testid="chart-result">
      <Card>
        <div className="flex items-center gap-2 flex-wrap">
          <Chip tone={t.tone}>{t.label}</Chip>
          {r.symbol && <Chip>{r.symbol}</Chip>}
          {r.timeframe && <Chip>{r.timeframe}</Chip>}
        </div>
        <div className="flex items-start gap-3 mt-3">
          <Icon className={`w-8 h-8 shrink-0 ${t.cls}`} strokeWidth={1.75} aria-hidden />
          <p className="font-bzserif text-[22px] sm:text-[24px] font-semibold leading-snug">{r.summary || "Here's the read."}</p>
        </div>
      </Card>
      <div className="grid gap-3 sm:grid-cols-2">
        <Card><Label tone="bear">Resistance (ceilings)</Label><List items={r.resistance} /></Card>
        <Card><Label tone="bull">Support (floors)</Label><List items={r.support} /></Card>
        {r.rsi_read && <Card><Label>RSI read</Label><p className="text-[15px]">{r.rsi_read}</p></Card>}
        {(r.patterns || []).length > 0 && <Card><Label>Patterns</Label><List items={r.patterns} /></Card>}
      </div>
      {(r.what_to_watch || []).length > 0 && (
        <Card><Label>What to watch</Label><ul className="space-y-1.5 text-[15px] list-disc pl-5">{r.what_to_watch.map((w, i) => <li key={i}>{w}</li>)}</ul></Card>
      )}
      <UsageLine usage={r.usage} what="chart reads" />
      <Disclaimer text={`Read from your image by AI; levels are approximate. ${r.disclaimer || ""}`} />
    </div>
  );
}

export default function ChartReader() {
  const { refreshMe } = useAuth();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [symbol, setSymbol] = useState("");
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    if (!file) { setPreview(null); return undefined; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const pick = (f) => {
    setState({ status: "idle" });
    if (f && f.size > MAX_MB * 1024 * 1024) { setFile(null); setState({ status: "error", msg: `That image is over ${MAX_MB} MB. Try a smaller screenshot.` }); return; }
    setFile(f || null);
  };

  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  // Wait `secs` with a visible countdown; resolves false if the member left the page.
  const countdown = async (secs, attempt) => {
    for (let left = secs; left > 0; left -= 1) {
      if (!alive.current) return false;
      setState({ status: "waiting", left, attempt });
      await sleep(1000);
    }
    return alive.current;
  };

  const read = async () => {
    if (!file) return;
    track("tool_opened", { tool: "chart" });
    const fd = new FormData();
    fd.append("file", file);
    if (symbol.trim()) fd.append("symbol", symbol.trim().toUpperCase());
    for (let attempt = 0; ; attempt += 1) {
      setState({ status: "loading" });
      try {
        const { data } = await api.post("/chart", fd, { headers: { "Content-Type": "multipart/form-data" }, _silentGate: true, timeout: 120000 });
        if (!alive.current) return;
        setState({ status: "done", data: data || {} });
        refreshMe();
        return;
      } catch (e) {
        if (!alive.current) return;
        const st = e?.response?.status;
        const d = e?.response?.data?.detail;
        if (st === 503 && d?.code === "unavailable" && attempt < AUTO_RETRIES) {
          const wait = Math.min(60, Math.max(5, Number(e?.response?.headers?.["retry-after"]) || d.retry_after || 15));
          if (await countdown(wait, attempt + 1)) continue;
          return;
        }
        if (d?.code === "not_chart") setState({ status: "error", msg: d.msg || "That doesn't look like a price chart. Upload a screenshot with candles or a price line." });
        else if ((st === 402 || st === 403) && d) setState({ status: "gate", detail: d });
        else setState({ status: "error", msg: apiError(e) });
        return;
      }
    }
  };

  const header = <PageHeader eyebrow={["Chart", "_Reader"]} title="Send a chart," accent="get a read." sub="Take a screenshot of any crypto price chart from your exchange or app. We tell you the trend, the floors and ceilings, and what to watch." />;
  return (
    <Gate feature="chart" header={header}>
      <div className="space-y-4">
        {header}
        <Card className="space-y-3">
          <label className="block border-2 border-dashed border-bz-line-strong rounded-bzcard p-6 text-center cursor-pointer hover:bg-bz-inset" data-testid="chart-drop">
            <ImagePlus className="w-8 h-8 mx-auto text-bz-gold" strokeWidth={1.6} aria-hidden />
            <span className="block text-[15px] font-semibold mt-2">{file ? file.name : "Choose a chart screenshot"}</span>
            <span className="block text-[13px] text-bz-muted mt-1">PNG or JPG, up to {MAX_MB} MB. Candles, bars or a price line.</span>
            <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" data-testid="chart-file" onChange={(e) => pick(e.target.files?.[0])} />
          </label>
          {preview && <img src={preview} alt="Your chart" className="max-h-72 mx-auto rounded-bzbtn border border-bz-line" />}
          <Field label="Which coin? (optional)"><Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="e.g. BTC" maxLength={15} data-testid="chart-symbol" /></Field>
          <Button className="w-full" disabled={!file || state.status === "waiting"} loading={state.status === "loading"} onClick={read} data-testid="chart-submit">Read my chart</Button>
          <p className="text-[12px] text-bz-muted">The image is read and not kept.</p>
        </Card>
        {state.status === "loading" && <Card><Spinner label="Reading your chart. This takes up to 30 seconds" /></Card>}
        {state.status === "waiting" && (
          <Card inset data-testid="chart-waiting">
            <p className="text-[15px]" role="status">Lots of people are reading charts right now. Trying again in {state.left}s…</p>
            <p className="text-[12px] text-bz-muted mt-1">This doesn't use up a chart read. Attempt {state.attempt + 1} of {AUTO_RETRIES + 1}.</p>
          </Card>
        )}
        {state.status === "error" && <Card inset><p className="text-[15px] text-bz-miss" role="alert">{state.msg}</p></Card>}
        {state.status === "gate" && <LockCard feature="chart" planNeeded={state.detail.plan_needed} kind={state.detail.code === "limit" ? "limit" : "locked"} used={state.detail.used} limit={state.detail.limit} msg={state.detail.msg} />}
        {state.status === "done" && <ChartResult r={state.data} />}
      </div>
    </Gate>
  );
}
