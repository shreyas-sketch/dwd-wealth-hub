// /app/inbox — alerts list + mark all read.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, CalendarDays, Gift, Layers, Radar, Repeat, Scale } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { ago } from "@/lib/format";
import { Button, Empty, Loadable, PageHeader } from "../components/ui";

const ICON = { verdict: Scale, verdict_changed: Scale, crash: AlertTriangle, dca: Repeat, autopilot: Repeat, basket: Layers, radar: Radar, calendar: CalendarDays, airdrop: Gift };

function isInternal(link) {
  return link && link.startsWith("/") && !link.startsWith("//");
}

export default function Inbox() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["inbox"], queryFn: async () => (await api.get("/inbox")).data });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const readAll = async () => {
    setErr(""); setBusy(true);
    try {
      await api.post("/inbox/read-all");
      qc.setQueryData(["inbox"], (d) => d && ({ ...d, unread: 0, items: (d.items || []).map((i) => ({ ...i, read: true })) }));
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  const unread = q.data?.unread || 0;
  return (
    <div className="space-y-4">
      <PageHeader eyebrow={["Your", "_Inbox"]} title="Alerts," accent="in one place." sub="Verdict changes, autopilot buys, market drops, basket changes and more."
        right={unread > 0 ? <Button variant="small" onClick={readAll} loading={busy} data-testid="inbox-read-all">Mark all read</Button> : null} />
      {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
      <Loadable q={q} what="your inbox" lines={5}>
        {(d) => (d.items || []).length ? (
          <ul className="rounded-bzcard border border-bz-line bg-bz-card divide-y divide-bz-line overflow-hidden" data-testid="inbox-list">
            {d.items.map((i) => {
              const Icon = ICON[i.kind] || Bell;
              const body = (
                <div className={`flex gap-3 px-4 py-3.5 ${i.read ? "" : "bg-bz-gold-tint"}`}>
                  <span className="w-9 h-9 rounded-full bg-bz-inset grid place-items-center shrink-0"><Icon className="w-[18px] h-[18px] text-bz-gold" strokeWidth={1.75} aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className={`text-[15px] ${i.read ? "font-medium" : "font-semibold"}`}>{i.title}</p>
                      {!i.read && <span className="w-2 h-2 rounded-full bg-bz-gold mt-2 shrink-0" aria-label="Unread" />}
                    </div>
                    {i.body && <p className="text-[14px] text-bz-muted mt-0.5">{i.body}</p>}
                    <p className="text-[12px] text-bz-muted mt-1">{ago(i.at)}</p>
                  </div>
                </div>
              );
              return (
                <li key={i.id}>
                  {isInternal(i.link) ? <Link to={i.link} className="block hover:bg-bz-inset">{body}</Link>
                    : i.link ? <a href={i.link} target="_blank" rel="noopener noreferrer" className="block hover:bg-bz-inset">{body}</a> : body}
                </li>
              );
            })}
          </ul>
        ) : <Empty icon={Bell} title="No alerts yet" sub="When a verdict changes, an autopilot buys, or the market drops, you'll see it here." />}
      </Loadable>
    </div>
  );
}
