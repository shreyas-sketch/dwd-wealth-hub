// Coin X-Ray: one input → a plain safe / risky / likely-scam answer. Used on the public page and /app/xray.
import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, ScanSearch, XCircle } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { track } from "@/lib/attribution";
import { usd, usdShort } from "@/lib/format";
import { Button, Card, Chip, Disclaimer, Label, LinkButton, Meter } from "./ui";
import { LockCard, Move, UsageLine, VerdictChip, XRAY } from "./common";
import { newAccountLine, signupLabel, useTrialDays } from "@/lib/trial";

const SEV = { high: "bear", medium: "gold", low: "muted" };
const KIND = { coin: "Coin", link: "Link", message: "Message" };

function Fact({ k, v }) {
  if (v === null || v === undefined || v === "") return null;
  return (
    <div className="flex justify-between gap-3 py-2 border-b border-bz-line last:border-0 text-[14px]">
      <span className="text-bz-muted">{k}</span>
      <span className="font-semibold text-right break-all">{v}</span>
    </div>
  );
}

export function XrayResult({ r }) {
  const { user } = useAuth();
  const x = XRAY[r.label] || { label: r.label || "Unknown", tone: "muted", bar: "gold" };
  const c = r.coin;
  const score = Math.max(0, Math.min(100, Number(r.score) || 0));
  return (
    <div className="space-y-3 rise-in" data-testid="xray-result">
      <Card className={r.label === "likely_scam" ? "border-bz-miss" : r.label === "safe" ? "border-bz-accent" : "border-bz-gold"}>
        <div className="flex items-center gap-2 flex-wrap">
          <Chip tone={x.tone} className="text-[12px] px-2.5 py-1">{x.label}</Chip>
          {r.kind && <Chip>{KIND[r.kind] || r.kind}</Chip>}
        </div>
        <p className="font-bzserif text-[24px] sm:text-[28px] font-semibold leading-snug mt-3" data-testid="xray-headline">{r.headline || "Here is what we found."}</p>
        <div className="mt-4">
          <div className="flex justify-between text-[13px] mb-1.5">
            <span className="font-semibold">Risk score</span>
            <span className="tabular font-semibold">{score} / 100</span>
          </div>
          <Meter value={score} tone={x.bar} label="Risk score" />
          <div className="flex justify-between text-[11px] text-bz-muted mt-1"><span>Lower risk</span><span>Higher risk</span></div>
        </div>
        {r.query && <p className="text-[12px] text-bz-muted mt-3 break-all">You checked: {r.query}</p>}
      </Card>

      {r.red_flags?.length > 0 && (
        <Card>
          <Label tone="bear">Red flags ({r.red_flags.length})</Label>
          <ul className="space-y-3">
            {r.red_flags.map((f, i) => (
              <li key={i} className="flex gap-2.5">
                <XCircle className="w-5 h-5 text-bz-miss shrink-0 mt-0.5" aria-hidden />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap"><span className="font-semibold text-[15px]">{f.title}</span>{f.severity && <Chip tone={SEV[f.severity] || "muted"}>{f.severity}</Chip>}</div>
                  {f.detail && <p className="text-[14px] text-bz-muted mt-0.5">{f.detail}</p>}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {r.green_flags?.length > 0 && (
        <Card>
          <Label tone="bull">Good signs</Label>
          <ul className="space-y-2">
            {r.green_flags.map((g, i) => (
              <li key={i} className="flex gap-2.5 text-[15px]"><CheckCircle2 className="w-5 h-5 text-bz-accent shrink-0 mt-0.5" aria-hidden />{g}</li>
            ))}
          </ul>
        </Card>
      )}

      {(c || r.what_it_does) && (
        <div className="grid gap-3 sm:grid-cols-2">
          {c && (
            <Card>
              <Label>Coin facts</Label>
              <Fact k="Coin" v={[c.name, c.symbol && `(${c.symbol})`].filter(Boolean).join(" ")} />
              <Fact k="Rank by size" v={c.rank != null ? `#${c.rank}` : null} />
              <Fact k="Price" v={c.price_usd != null ? usd(c.price_usd) : null} />
              <Fact k="24h change" v={c.change_24h != null ? <Move v={c.change_24h} /> : null} />
              <Fact k="Market value" v={c.market_cap_usd != null ? usdShort(c.market_cap_usd) : null} />
              <Fact k="Traded in 24h" v={c.volume_24h_usd != null ? usdShort(c.volume_24h_usd) : null} />
              <Fact k="Age" v={c.age_days != null ? `${Number(c.age_days).toLocaleString("en-IN")} days` : null} />
              <Fact k="Chain" v={c.chain} />
              <Fact k="Contract" v={c.contract} />
            </Card>
          )}
          {r.what_it_does && (
            <Card>
              <Label>What it does</Label>
              <p className="text-[15px] leading-relaxed">{r.what_it_does}</p>
              {r.verdict && (
                <div className="mt-4 pt-3 border-t border-bz-line">
                  <Label className="mb-1.5">Today's verdict</Label>
                  <div className="flex items-center gap-2 flex-wrap">
                    <VerdictChip v={r.verdict.verdict} conf={r.verdict.confidence} />
                    {user && r.verdict.symbol && <Link to={`/app/coin/${r.verdict.symbol}`} className="text-sm font-semibold text-bz-accent">Open coin page</Link>}
                  </div>
                  {r.verdict.summary && <p className="text-[14px] text-bz-muted mt-1.5">{r.verdict.summary}</p>}
                </div>
              )}
            </Card>
          )}
        </div>
      )}
      <UsageLine usage={r.usage} what="checks" />
      <Disclaimer text={r.disclaimer} />
    </div>
  );
}

export default function XrayBox({ onDone, autoFocus = false }) {
  const { user } = useAuth();
  const trialDays = useTrialDays();
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [state, setState] = useState({ status: "idle" });

  const run = async (e) => {
    e?.preventDefault();
    const q = query.trim();
    if (!q) return;
    setState({ status: "loading" });
    track("tool_opened", { tool: "xray", anon: !user });
    try {
      const { data } = await api.post("/xray", { query: q }, { _silentGate: true });
      setState({ status: "done", data: data || {} });
      if (user) qc.invalidateQueries({ queryKey: ["xray-history"] });
      onDone?.(data);
    } catch (err) {
      const st = err?.response?.status;
      const d = err?.response?.data?.detail;
      if (st === 402 || d?.code === "limit") setState({ status: "limit", detail: d || {} });
      else setState({ status: "error", msg: apiError(err) });
    }
  };

  return (
    <div className="space-y-3">
      <form onSubmit={run}>
        <label htmlFor="xray-input" className="block text-[15px] font-semibold mb-2">Paste a coin name, contract address, link or WhatsApp tip</label>
        <textarea id="xray-input" data-testid="xray-input" value={query} onChange={(e) => setQuery(e.target.value)} rows={3} autoFocus={autoFocus}
          placeholder={"e.g. Pepe · 0x6982… · https://… · \"Double your USDT in 7 days, join our group\""}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && query.length < 80) { e.preventDefault(); run(); } }}
          className="w-full rounded-bzbtn border border-bz-line-strong bg-bz-card text-bz-ink px-3.5 py-3 text-[16px] placeholder:text-bz-muted outline-none focus:border-bz-accent resize-y min-h-[88px]" />
        <Button type="submit" className="w-full mt-2.5" data-testid="xray-submit" loading={state.status === "loading"} disabled={!query.trim()}>
          <ScanSearch className="w-4 h-4" aria-hidden /> {state.status === "loading" ? "Checking" : "X-Ray it"}
        </Button>
      </form>
      {state.status === "error" && <p className="text-sm text-bz-miss" role="alert">{state.msg}</p>}
      {state.status === "limit" && (user ? (
        <LockCard feature="xray" kind="limit" planNeeded={state.detail.plan_needed} used={state.detail.used} limit={state.detail.limit} msg={state.detail.msg} />
      ) : (
        <Card className="border-bz-gold" data-testid="xray-anon-limit">
          <p className="font-bzdisplay text-[22px] font-bold leading-tight">You've used today's free check.</p>
          <p className="text-[15px] text-bz-muted mt-1.5">{newAccountLine(trialDays)} It takes 30 seconds with your mobile number.</p>
          <LinkButton to="/login?next=/app/xray" className="w-full mt-4" data-testid="xray-signup">{signupLabel(trialDays)}</LinkButton>
        </Card>
      ))}
      {state.status === "done" && <XrayResult r={state.data} />}
    </div>
  );
}
