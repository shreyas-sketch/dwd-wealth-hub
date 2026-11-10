// /app/airdrops — live airdrops with a step checklist (tick → POST), X-Ray chip, deadline, reward, link.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, ExternalLink, Gift, Square } from "lucide-react";
import { useFeature } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { daysUntil, hdate } from "@/lib/format";
import { Card, Chip, Empty, Label, Loadable, Meter, PageHeader } from "../components/ui";
import { Gate, XrayChip } from "../components/common";

function AirdropCard({ a }) {
  const qc = useQueryClient();
  const done = new Set(a.done_steps || []);
  const steps = a.steps || [];
  const left = daysUntil(a.deadline);
  const tick = async (stepId, on) => {
    // optimistic tick, then take the server's item
    qc.setQueryData(["airdrops"], (d) => d && ({ ...d, items: (d.items || []).map((x) => x.id === a.id
      ? { ...x, done_steps: on ? [...(x.done_steps || []), stepId] : (x.done_steps || []).filter((s) => s !== stepId) } : x) }));
    try {
      const { data } = await api.post(`/airdrops/${a.id}/steps/${stepId}`, { done: on });
      if (data?.id) qc.setQueryData(["airdrops"], (d) => d && ({ ...d, items: (d.items || []).map((x) => (x.id === a.id ? data : x)) }));
    } catch { qc.invalidateQueries({ queryKey: ["airdrops"] }); }
  };
  const progress = steps.length ? (done.size / steps.length) * 100 : 0;
  return (
    <Card data-testid={`airdrop-${a.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[18px] font-semibold">{a.name}</h3>
          <p className="text-[13px] text-bz-muted">{[a.coin, a.chain].filter(Boolean).join(" · ")}</p>
        </div>
        <Chip tone={a.status === "live" ? "bull" : "muted"}>{a.status === "live" ? "Live" : "Ended"}</Chip>
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        {a.link_verified && <Chip tone="bull">Verified official link</Chip>}
        {a.xray && <XrayChip label={a.xray.label} score={a.xray.score} />}
        {a.deadline && <Chip tone={left != null && left <= 3 ? "bear" : "gold"}>Ends {hdate(a.deadline)}{left != null ? ` · ${left} day${left === 1 ? "" : "s"} left` : ""}</Chip>}
      </div>
      {a.reward && <p className="text-[15px] mt-3"><b>Reward:</b> {a.reward}</p>}
      {a.description && <p className="text-[14.5px] text-bz-muted mt-1.5">{a.description}</p>}
      {steps.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-1.5"><Label className="mb-0">Steps</Label><span className="text-[12px] text-bz-muted tabular">{done.size} of {steps.length} done</span></div>
          <Meter value={progress} className="mb-2" label="Steps done" />
          <ul className="divide-y divide-bz-line">
            {steps.map((s, i) => {
              const on = done.has(s.id);
              return (
                <li key={s.id}>
                  <button type="button" onClick={() => tick(s.id, !on)} aria-pressed={on} data-testid={`step-${a.id}-${s.id}`}
                    className="w-full flex items-start gap-3 py-3 text-left min-h-[48px]">
                    {on ? <CheckSquare className="w-5 h-5 text-bz-accent shrink-0 mt-0.5" aria-hidden /> : <Square className="w-5 h-5 text-bz-muted shrink-0 mt-0.5" aria-hidden />}
                    <span className={`text-[15px] ${on ? "line-through text-bz-muted" : ""}`}><span className="text-bz-muted mr-1">{i + 1}.</span>{s.text}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {a.link && (
        <a href={a.link} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-bz-accent min-h-[40px]">
          Open the airdrop page <ExternalLink className="w-3.5 h-3.5" aria-hidden />
        </a>
      )}
    </Card>
  );
}

export default function Airdrops() {
  const header = <PageHeader eyebrow={["Airdrop", "_Finder"]} title="Free tokens," accent="checked first." sub="Projects give away tokens to early users. We list the live ones, X-Ray each for scams, and give you the steps." />;
  const can = useFeature("airdrops");
  const q = useQuery({ queryKey: ["airdrops"], queryFn: async () => (await api.get("/airdrops")).data, enabled: can });
  return (
    <Gate feature="airdrops" header={header}>
      <div className="space-y-4">
        {header}
        <Card inset><p className="text-[14px]"><b>Never</b> share your seed phrase or private key, and never send money to "unlock" an airdrop. Real airdrops don't ask for that.</p></Card>
        <Loadable q={q} what="airdrops" lines={5}>
          {(d) => {
            const items = (d.items || []).slice().sort((x, y) => (x.status === "live" ? 0 : 1) - (y.status === "live" ? 0 : 1));
            return items.length ? (
              <div className="grid gap-3 md:grid-cols-2 items-start">{items.map((a) => <AirdropCard key={a.id} a={a} />)}</div>
            ) : <Empty icon={Gift} title="No live airdrops right now" sub="We add new ones as they open. You'll get an alert in your inbox." />;
          }}
        </Loadable>
      </div>
    </Gate>
  );
}
