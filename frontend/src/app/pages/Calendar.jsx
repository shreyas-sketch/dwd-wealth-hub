// /app/calendar — crypto events grouped by date: impact chip, "Yours" marker, kind icon.
import { useQuery } from "@tanstack/react-query";
import { Bitcoin, CalendarDays, Landmark, ListPlus, LockOpen, TrendingUp, Wrench } from "lucide-react";
import { useFeature } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { istToday } from "@/lib/format";
import { Card, Chip, Empty, Loadable, PageHeader } from "../components/ui";
import { Gate } from "../components/common";

const KIND = {
  unlock: { label: "Token unlock", icon: LockOpen },
  listing: { label: "Listing", icon: ListPlus },
  upgrade: { label: "Upgrade", icon: Wrench },
  halving: { label: "Halving", icon: Bitcoin },
  macro: { label: "Economy", icon: Landmark },
  etf: { label: "ETF", icon: TrendingUp },
};
const IMPACT = { high: "bear", medium: "gold", low: "muted" };
const WINDOW_DAYS = 60;

function windowEnd() {
  const d = new Date(`${istToday()}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + WINDOW_DAYS);
  return d.toISOString().slice(0, 10);
}

function dayHeading(iso) {
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  const today = new Date(`${istToday()}T00:00:00Z`);
  const diff = Math.round((d - today) / 86400000);
  // The year is shown when it isn't this year (QA 10 Nov: "Saturday, 15 April" was the 2028 halving).
  const otherYear = d.getUTCFullYear() !== today.getUTCFullYear();
  const label = d.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC", ...(otherYear ? { year: "numeric" } : {}) });
  return diff === 0 ? `Today · ${label}` : diff === 1 ? `Tomorrow · ${label}` : label;
}

function DaySection({ date, evs }) {
  return (
    <section data-testid={`cal-${date}`}>
      <h2 className="font-bzmono text-[11px] uppercase tracking-[0.2em] text-bz-gold-deep mb-2">{dayHeading(date)}</h2>
      <div className="space-y-2">
        {evs.map((e) => {
          const k = KIND[e.kind] || { label: e.kind, icon: CalendarDays };
          const Icon = k.icon;
          return (
            <Card key={e.id || e.title} className={`p-4 ${e.yours ? "border-bz-gold" : ""}`}>
              <div className="flex gap-3">
                <span className="w-10 h-10 rounded-full bg-bz-inset grid place-items-center shrink-0"><Icon className="w-5 h-5 text-bz-gold" strokeWidth={1.75} aria-hidden /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[15.5px] font-semibold">{e.title}</p>
                    {e.yours && <Chip tone="solid">Yours</Chip>}
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    <Chip>{k.label}</Chip>
                    {e.impact && <Chip tone={IMPACT[e.impact] || "muted"}>{e.impact} impact</Chip>}
                    {(e.coins || []).map((c) => <Chip key={c} tone="gold">{c}</Chip>)}
                  </div>
                  {e.note && <p className="text-[14px] text-bz-muted mt-2">{e.note}</p>}
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

export default function Calendar() {
  const can = useFeature("calendar");
  const q = useQuery({ queryKey: ["calendar"], queryFn: async () => (await api.get("/calendar", { params: { days: 60 } })).data, enabled: can });
  const header = <PageHeader eyebrow={["Events", "_Calendar"]} title="Dates that" accent="move prices." sub="Token unlocks, exchange listings, network upgrades and big economy news for the next 60 days. Coins you follow are marked Yours." />;
  return (
    <Gate feature="calendar" header={header}>
      <div className="space-y-5">
        {header}
        <Loadable q={q} what="the calendar" lines={6}>
          {(d) => {
            const items = (d.items || []).slice().sort((a, b) => String(a.date).localeCompare(String(b.date)));
            const end = windowEnd();
            const soon = items.filter((e) => String(e.date).slice(0, 10) <= end);
            const later = items.filter((e) => String(e.date).slice(0, 10) > end);   // e.g. the next halving
            const group = (list) => Object.entries(list.reduce((m, e) => { const k = String(e.date).slice(0, 10); (m[k] = m[k] || []).push(e); return m; }, {}));
            return (
              <>
                {!soon.length && <Empty icon={CalendarDays} title={`No events in the next ${WINDOW_DAYS} days`} sub="New events are added as they're announced." />}
                {group(soon).map(([date, evs]) => <DaySection key={date} date={date} evs={evs} />)}
                {later.length > 0 && (
                  <div className="space-y-5" data-testid="cal-later">
                    <h2 className="font-bzdisplay text-[18px] font-bold pt-2">Further ahead</h2>
                    {group(later).map(([date, evs]) => <DaySection key={date} date={date} evs={evs} />)}
                  </div>
                )}
              </>
            );
          }}
        </Loadable>
      </div>
    </Gate>
  );
}
