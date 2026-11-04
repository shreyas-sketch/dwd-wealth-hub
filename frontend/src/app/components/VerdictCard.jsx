// One coin's daily verdict: chip + confidence, summary, bull / bear points and the chair (lite+), watch star.
import { Link } from "react-router-dom";
import { usd } from "@/lib/format";
import { Card, Chip } from "./ui";
import { CoinBadge, Move, VERDICT_TEXT, VerdictChip, WatchStar } from "./common";

export function Points({ bull = [], bear = [], chair }) {
  if (!bull?.length && !bear?.length && !chair) return null;
  const side = (title, tone, pts) => (pts?.length ? (
    <div className="rounded-bzbtn border border-bz-line bg-bz-panel px-3.5 py-3">
      <div className={`text-[14px] font-semibold ${tone}`}>{title}</div>
      <ul className="text-[14.5px] mt-1.5 space-y-1.5 list-disc pl-4">{pts.map((x, i) => <li key={i}>{typeof x === "string" ? x : x?.point}</li>)}</ul>
    </div>
  ) : null);
  return (
    <div className="mt-3 space-y-2">
      <div className="grid gap-2 sm:grid-cols-2">
        {side("The case for", "text-bz-accent", bull)}
        {side("The case against", "text-bz-miss", bear)}
      </div>
      {chair && <p className="text-[14.5px]"><span className="font-semibold">The chair:</span> {chair}</p>}
    </div>
  );
}

export default function VerdictCard({ v, wl, details = true }) {
  return (
    <Card className="p-4 sm:p-5" data-testid={`verdict-${v.symbol}`}>
      <div className="flex items-start gap-3">
        <CoinBadge symbol={v.symbol} />
        <Link to={`/app/coin/${v.symbol}`} className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2 flex-wrap">
            <span className="text-[17px] font-semibold">{v.name || v.symbol}</span>
            <span className="text-[14px] text-bz-muted">{v.symbol}</span>
          </span>
          <span className="flex items-baseline gap-2 text-[14px] mt-0.5">
            <span className="tabular">{usd(v.price_usd)}</span><Move v={v.change_24h} className="text-[13px]" />
          </span>
        </Link>
        {wl && <WatchStar symbol={v.symbol} watched={v.watched} wl={wl} />}
      </div>
      <div className="mt-3 flex items-center gap-2 flex-wrap">
        <span className={`font-bzdisplay text-[26px] font-bold leading-none ${VERDICT_TEXT[v.verdict] || ""}`}>{v.verdict || "—"}</span>
        {v.confidence != null && <span className="text-[14px] text-bz-muted">{v.confidence}% confidence</span>}
        {v.changed_from && <Chip tone="gold">Changed from {v.changed_from}</Chip>}
      </div>
      {v.summary && <p className="text-[15px] mt-2">{v.summary}</p>}
      {details && <Points bull={v.bull} bear={v.bear} chair={v.chair} />}
      <Link to={`/app/coin/${v.symbol}`} className="inline-block mt-3 text-sm font-semibold text-bz-accent">Forecast and debate</Link>
    </Card>
  );
}

export { VerdictChip };
