// Admin › Webinar: date range → report + "Download Day 3 list (CSV)".
import { useState } from "react";
import { Download } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { Card, Field, Input } from "../components/ui";
import { AdminH, AdminLoadable, Kpi, KpiGrid, Table, useAdmin } from "./shared";

// Calendar date in India (the backend reads these dates as IST days).
const iso = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(d);

export default function Webinar() {
  const today = new Date();
  const [range, setRange] = useState({ start: iso(new Date(today.getTime() - 2 * 86400000)), end: iso(today) });
  const ok = range.start && range.end && range.start <= range.end;
  const q = useAdmin("webinar", range, { enabled: !!ok });
  const csv = `${API_BASE}/admin/webinar/day3.csv?start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}`;
  return (
    <div className="space-y-4">
      <Card>
        <div className="grid grid-cols-2 gap-3 max-w-[460px]">
          <Field label="From"><Input type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} data-testid="webinar-start" /></Field>
          <Field label="To"><Input type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} data-testid="webinar-end" /></Field>
        </div>
        {!ok && <p className="text-sm text-bz-miss mt-2">The start date must be on or before the end date.</p>}
        <p className="text-[13px] text-bz-muted mt-2">Accounts created in this window (webinar days 1–3).</p>
      </Card>
      {ok && (
        <AdminLoadable q={q} what="the webinar report">
          {(d) => (
            <div className="space-y-4">
              <KpiGrid cols="grid-cols-2 md:grid-cols-5">
                <Kpi label="Signups" value={d.signups} />
                <Kpi label="Logins" value={d.logins} />
                <Kpi label="Bought ₹2,000" value={d.bought?.lite ?? 0} tone="up" />
                <Kpi label="Bought ₹5,000" value={d.bought?.pro ?? 0} tone="up" />
                <Kpi label="Day 3 list" value={d.day3_list_count} tone="gold" sub="Signed up, not paid" />
              </KpiGrid>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <a href={csv} className="inline-flex items-center gap-2 min-h-[48px] px-6 rounded-full bg-bz-btn text-bz-on-btn text-[16px] font-semibold hover:opacity-90" data-testid="webinar-csv">
                  <Download className="w-4 h-4" aria-hidden /> Download the Day 3 list
                </a>
                <span className="text-[14px] text-bz-muted">A CSV of the {Number(d.day3_list_count || 0).toLocaleString("en-IN")} people to call for the ₹2,000 plan.</span>
              </div>
              <Card>
                <AdminH>Tools used in this window</AdminH>
                <Table rows={d.feature_usage} cols={[
                  { key: "feature", label: "Tool" },
                  { key: "users", label: "People", right: true },
                  { key: "uses", label: "Uses", right: true },
                ]} empty="No usage in this window." />
              </Card>
            </div>
          )}
        </AdminLoadable>
      )}
    </div>
  );
}
