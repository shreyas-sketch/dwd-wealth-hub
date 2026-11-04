// Admin › Vendors: live / fake / off, plus the AI queues (one pool per model class) for watching a webinar.
import { Card, Chip, Label } from "../components/ui";
import { AdminLoadable, Table, useAdmin } from "./shared";

const TONE = { live: "bull", fake: "gold", off: "muted" };
const POOL = { fast: "Fast (X-Ray, news)", strong: "Strong (Ask, verdicts, debate)", vision: "Vision (Chart Reader)" };

export default function AdminVendors() {
  const q = useAdmin("vendors", null, { refetchInterval: 10_000 });
  return (
    <div className="space-y-3">
      <Card inset><p className="text-sm">"Live" calls the real service. "Fake" returns sample data (QA mode or a missing key). "Off" means the feature using it is disabled.</p></Card>
      <AdminLoadable q={q} what="vendors">
        {(d) => (
          <>
            <Card className="px-0 sm:px-5 py-2">
              <Table rows={d.vendors || []} empty="No vendors." cols={[
                { key: "name", label: "Vendor", render: (r) => <b>{r.name}</b> },
                { key: "mode", label: "Mode", render: (r) => <Chip tone={TONE[r.mode] || "bear"}>{r.mode}</Chip> },
              ]} />
            </Card>
            {(d.ai_pools || []).length > 0 && (
              <Card className="px-0 sm:px-5 py-2 space-y-2" data-testid="ai-pools">
                <div className="px-4 sm:px-0 pt-2">
                  <Label>AI queues (this server worker, refreshes every 10 s)</Label>
                  <p className="text-[12px] text-bz-muted mt-1">"Turned away" counts requests that waited the full queue time; members were told to try again and their use was refunded. If it climbs during a webinar, raise the Anthropic limit or the pool size.</p>
                </div>
                <Table rows={d.ai_pools.map((p) => ({ ...p, id: p.pool }))} cols={[
                  { key: "pool", label: "Pool", wrap: true, render: (r) => <b>{POOL[r.pool] || r.pool}</b> },
                  { key: "busy", label: "Running", right: true, render: (r) => `${r.in_flight} / ${r.size}` },
                  { key: "waiting", label: "Waiting", right: true },
                  { key: "queue_wait_s", label: "Max wait", right: true, render: (r) => `${r.queue_wait_s} s` },
                  { key: "rejected", label: "Turned away", right: true, render: (r) => <span className={r.rejected ? "text-bz-miss font-semibold" : ""}>{r.rejected}</span> },
                ]} />
              </Card>
            )}
          </>
        )}
      </AdminLoadable>
    </div>
  );
}
