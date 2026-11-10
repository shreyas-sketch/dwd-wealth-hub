// /app/xray — Coin X-Ray full page: checker, usage line, history.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago } from "@/lib/format";
import XrayBox from "../components/Xray";
import { Card, Chip, Empty, ErrorCard, Label, PageHeader, Skeleton } from "../components/ui";
import { Gate, UsageLine, XRAY } from "../components/common";

const KIND = { coin: "Coin", link: "Link", message: "Message" };

function HistoryList() {
  const q = useQuery({ queryKey: ["xray-history"], queryFn: async () => (await api.get("/xray/history")).data });
  if (q.isLoading) return <Card><Skeleton lines={3} /></Card>;
  if (q.isError) return <ErrorCard error={q.error} onRetry={() => q.refetch()} what="your checks" />;
  const items = q.data?.items || [];
  if (!items.length) return <Empty icon={History} title="No checks yet" sub="Everything you X-Ray shows up here, so you can look back at it." />;
  return (
    <Card>
      <Label>Your recent checks</Label>
      <ul className="divide-y divide-bz-line" data-testid="xray-history">
        {items.map((h, i) => {
          const x = XRAY[h.label];
          return (
            <li key={`${h.at}-${i}`} className="py-3 flex items-start justify-between gap-3">
              <span className="min-w-0">
                <span className="block text-[15px] font-semibold break-words line-clamp-2">{h.query}</span>
                <span className="block text-[12px] text-bz-muted mt-0.5">{KIND[h.kind] || h.kind}{h.at ? ` · ${ago(h.at)}` : ""}</span>
              </span>
              <span className="flex flex-col items-end gap-1 shrink-0">
                {x && <Chip tone={x.tone}>{x.label}</Chip>}
                {h.score != null && <span className="text-[12px] text-bz-muted tabular">Risk {h.score}</span>}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export default function XrayPage() {
  const { plan, refreshMe } = useAuth();
  const [checked, setChecked] = useState(false);     // after a check, the result shows the up-to-date usage line
  const header = <PageHeader eyebrow={["Coin", "_X-Ray"]} title="Is it safe," accent="or a scam?" sub="Paste a coin name, contract address, link or a message you got. You get a plain answer in seconds." />;
  return (
    <Gate feature="xray" header={header}>
      <div className="space-y-5">
        {header}
        <Card>
          <XrayBox autoFocus onDone={() => { setChecked(true); refreshMe(); }} />
          {!checked && <UsageLine usage={plan?.limits?.xray} what="checks" className="mt-3" />}
        </Card>
        <HistoryList />
      </div>
    </Gate>
  );
}
