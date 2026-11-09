// Admin › Verdict accuracy: were the daily Bullish / Neutral / Bearish calls right after 7 and 30 days, and did
// they beat chance? Reads GET /admin/verdicts/accuracy (backend/features/accuracy.py explains the scoring).
import { useState } from "react";
import { sdate } from "@/lib/format";
import { Card, Chip, Segmented } from "../components/ui";
import { VERDICT_TEXT } from "../components/common";
import { AdminH, AdminLoadable, Kpi, KpiGrid, Table, useAdmin } from "./shared";

const pctOr = (v, d = 1) => (v == null ? "—" : `${Number(v).toFixed(d)}%`);
const signed = (v, unit = "%") => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Number(v)).toFixed(1)}${unit}`);
const range = (r) => (r?.[0] == null ? "" : `${r[0]}–${r[1]}%`);

function Edge({ v }) {
  if (v == null) return <span className="text-bz-muted">—</span>;
  const cls = v >= 5 ? "text-bz-accent" : v <= -5 ? "text-bz-miss" : "text-bz-muted";
  return <span className={`font-semibold tabular ${cls}`}>{signed(v, " pts")}</span>;
}

function Horizon({ h }) {
  return (
    <div className="space-y-5">
      <p className="text-[17px] max-w-[70ch]" data-testid="accuracy-headline">
        {h.calls ? (
          <>Over {h.horizon_days} days the verdicts were right <b className="tabular">{pctOr(h.hit_rate_pct)}</b> of the time
            {h.range_pct?.[0] != null && <> (likely between {range(h.range_pct)})</>}, across <b className="tabular">{h.calls.toLocaleString("en-IN")}</b> calls.</>
        ) : <>No verdicts are old enough to score at {h.horizon_days} days yet.</>}
      </p>
      {h.calls > 0 && !h.enough_data && (
        <p className="rounded-bzbtn bg-bz-gold-tint text-bz-gold-deep px-3.5 py-2.5 text-[15px] font-semibold" role="status">
          Fewer than 30 calls so far. Treat these numbers as luck until more verdicts are scored.
        </p>
      )}
      <KpiGrid cols="grid-cols-2 md:grid-cols-4">
        <Kpi label="Right" value={pctOr(h.hit_rate_pct)} sub={h.range_pct?.[0] != null ? `95% range ${range(h.range_pct)}` : null} />
        <Kpi label="Calls scored" value={(h.calls || 0).toLocaleString("en-IN")} />
        <Kpi label="Bullish minus Bearish" value={signed(h.spread_pct)} tone={h.spread_pct > 0 ? "up" : undefined}
          sub="Above zero: calls point the right way" />
        <Kpi label="Counts as a move" value={`±${h.band_pct}%`} sub={`Smaller ${h.horizon_days}-day moves count as Neutral`} />
      </KpiGrid>

      <Card className="px-0 sm:px-5 py-4">
        <div className="px-4 sm:px-0"><AdminH>By verdict, against chance</AdminH>
          <p className="text-[14px] text-bz-muted -mt-1.5 mb-2 max-w-[75ch]">"Chance" is how often the same verdict would have been right if it were given for every coin on every day. The edge is the difference: a verdict with no edge adds nothing.</p></div>
        <Table rows={(h.by_verdict || []).map((r) => ({ ...r, id: r.verdict }))} cols={[
          { key: "verdict", label: "Verdict", render: (r) => <b className={VERDICT_TEXT[r.verdict]}>{r.verdict}</b> },
          { key: "calls", label: "Calls", right: true },
          { key: "hit_rate_pct", label: "Right", right: true, render: (r) => pctOr(r.hit_rate_pct) },
          { key: "chance_pct", label: "Chance", right: true, render: (r) => pctOr(r.chance_pct) },
          { key: "edge_pts", label: "Edge", right: true, render: (r) => <Edge v={r.edge_pts} /> },
          { key: "avg_return_pct", label: "Average move after", right: true, render: (r) => signed(r.avg_return_pct) },
        ]} />
      </Card>

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <Card className="px-0 sm:px-5 py-4">
          <div className="px-4 sm:px-0"><AdminH>By confidence</AdminH>
            <p className="text-[14px] text-bz-muted -mt-1.5 mb-2">Higher-confidence calls should be right more often. If they aren't, the confidence number means nothing.</p></div>
          <Table rows={(h.by_confidence || []).map((r) => ({ ...r, id: r.bucket }))} cols={[
            { key: "bucket", label: "Confidence" },
            { key: "calls", label: "Calls", right: true },
            { key: "hit_rate_pct", label: "Right", right: true, render: (r) => pctOr(r.hit_rate_pct) },
          ]} />
        </Card>
        <Card className="px-0 sm:px-5 py-4">
          <div className="px-4 sm:px-0"><AdminH>By coin</AdminH></div>
          <Table rows={(h.by_coin || []).map((r) => ({ ...r, id: r.symbol }))} empty="No coins scored yet." cols={[
            { key: "symbol", label: "Coin", render: (r) => <b>{r.symbol}</b> },
            { key: "calls", label: "Calls", right: true },
            { key: "hit_rate_pct", label: "Right", right: true, render: (r) => pctOr(r.hit_rate_pct) },
            { key: "avg_return_pct", label: "Average move", right: true, render: (r) => signed(r.avg_return_pct) },
          ]} />
        </Card>
      </div>
    </div>
  );
}

export default function AdminAccuracy() {
  const [days, setDays] = useState(90);
  const [hz, setHz] = useState(7);
  const q = useAdmin("verdicts/accuracy", { days });
  return (
    <div className="space-y-5">
      <p className="text-[16px] text-bz-muted max-w-[75ch]">
        Each daily verdict is checked 7 and 30 days later against the price when it was made. Bullish is right if the
        coin rose more than the band, Bearish if it fell more than the band, Neutral if it stayed inside it.
      </p>
      <div className="flex flex-wrap gap-3">
        <Segmented className="w-full sm:w-[300px]" label="Period" value={days} onChange={setDays} testid="acc-days"
          options={[{ value: 30, label: "30 days" }, { value: 90, label: "90 days" }, { value: 180, label: "180 days" }]} />
        <Segmented className="w-full sm:w-[260px]" label="Checked after" value={hz} onChange={setHz} testid="acc-h"
          options={[{ value: 7, label: "After 7 days" }, { value: 30, label: "After 30 days" }]} />
      </div>
      <AdminLoadable q={q} what="verdict accuracy">
        {(d) => {
          const h = (d.horizons || []).find((x) => x.horizon_days === hz);
          return (
            <div className="space-y-5">
              {h ? <Horizon h={h} /> : null}
              <Card className="px-0 sm:px-5 py-4">
                <div className="px-4 sm:px-0"><AdminH>Latest scored calls (7 days)</AdminH></div>
                <Table rows={(d.recent || []).map((r) => ({ ...r, id: `${r.date}:${r.symbol}` }))} empty="Nothing scored yet." cols={[
                  { key: "date", label: "Made on", render: (r) => sdate(r.date) },
                  { key: "symbol", label: "Coin", render: (r) => <b>{r.symbol}</b> },
                  { key: "verdict", label: "Verdict", render: (r) => <span className={VERDICT_TEXT[r.verdict]}>{r.verdict} · {r.confidence}%</span> },
                  { key: "return_pct", label: "Move after", right: true, render: (r) => signed(r.return_pct) },
                  { key: "correct", label: "Result", render: (r) => <Chip tone={r.correct ? "bull" : "bear"}>{r.correct ? "Right" : "Wrong"}</Chip> },
                ]} />
              </Card>
            </div>
          );
        }}
      </AdminLoadable>
    </div>
  );
}
