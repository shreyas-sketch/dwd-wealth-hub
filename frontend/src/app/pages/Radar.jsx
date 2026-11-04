// /app/radar — Early Coin Radar: new listings and trending coins, each auto-X-Rayed.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Radar as RadarIcon } from "lucide-react";
import { useFeature } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { ago, usd, venueName } from "@/lib/format";
import { Card, Chip, Empty, Loadable, PageHeader, Segmented } from "../components/ui";
import { CoinBadge, Gate, Move, XrayChip } from "../components/common";

const KIND = { new_listing: { label: "New listing", tone: "gold" }, trending: { label: "Trending", tone: "bull" } };

function RadarCard({ r }) {
  const k = KIND[r.kind] || { label: r.kind, tone: "muted" };
  const flags = r.xray?.red_flags || [];
  return (
    <Card className="p-4 min-w-0" data-testid={`radar-${r.id || r.symbol}`}>
      <div className="flex items-start gap-3">
        <CoinBadge symbol={r.symbol} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 flex-wrap"><span className="text-[16.5px] font-semibold">{r.name || r.symbol}</span><span className="font-bzmono text-[11px] uppercase tracking-[0.14em] text-bz-muted">{r.symbol}</span></div>
          <div className="flex items-center gap-2 flex-wrap mt-1.5">
            <Chip tone={k.tone}>{k.label}</Chip>
            {r.venue && <Chip>{venueName(r.venue)}</Chip>}
            {r.xray && <XrayChip label={r.xray.label} score={r.xray.score} />}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="tabular font-semibold">{usd(r.price_usd)}</div>
          <Move v={r.change_24h} className="text-[13px]" />
        </div>
      </div>
      {flags.length > 0 && (
        <ul className="mt-3 space-y-1 text-[13.5px]">
          {flags.slice(0, 4).map((f, i) => <li key={i} className="flex gap-2"><span className="text-bz-miss" aria-hidden>●</span><span>{f}</span></li>)}
        </ul>
      )}
      <p className="text-[12px] text-bz-muted mt-2">{r.listed_at ? `Listed ${ago(r.listed_at)}` : r.seen_at ? `Spotted ${ago(r.seen_at)}` : ""}</p>
    </Card>
  );
}

export default function Radar() {
  const can = useFeature("radar");
  const q = useQuery({ queryKey: ["radar"], queryFn: async () => (await api.get("/radar")).data, enabled: can });
  const [kind, setKind] = useState("all");
  const header = <PageHeader eyebrow={["Early", "_Coin radar"]} title="New coins," accent="checked early." sub="Coins just listed on Binance or KuCoin, and coins suddenly trending. Each one is X-Rayed for red flags. New does not mean safe." />;
  return (
    <Gate feature="radar" header={header}>
      <div className="space-y-4">
        {header}
        <Segmented options={[{ value: "all", label: "All" }, { value: "new_listing", label: "New listings" }, { value: "trending", label: "Trending" }]} value={kind} onChange={setKind} label="Filter" testid="radar-filter" />
        <Loadable q={q} what="the radar" lines={5}>
          {(d) => {
            const items = (d.items || []).filter((r) => kind === "all" || r.kind === kind);
            return (
              <>
                {d.as_of && <p className="text-[13px] text-bz-muted">Updated {ago(d.as_of)}</p>}
                {items.length ? <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{items.map((r) => <RadarCard key={r.id || r.symbol} r={r} />)}</div>
                  : <Empty icon={RadarIcon} title="Nothing on the radar yet" sub="We check for new listings and trending coins every hour." />}
              </>
            );
          }}
        </Loadable>
        <p className="text-[12px] text-bz-muted">Brand-new coins are the riskiest kind. Many fall sharply after listing. This is information, not a tip.</p>
      </div>
    </Gate>
  );
}
