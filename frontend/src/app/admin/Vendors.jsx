// Admin › Vendors: live / fake / off.
import { Card, Chip } from "../components/ui";
import { AdminLoadable, Table, useAdmin } from "./shared";

const TONE = { live: "bull", fake: "gold", off: "muted" };

export default function AdminVendors() {
  const q = useAdmin("vendors");
  return (
    <div className="space-y-3">
      <Card inset><p className="text-sm">"Live" calls the real service. "Fake" returns sample data (QA mode or a missing key). "Off" means the feature using it is disabled.</p></Card>
      <AdminLoadable q={q} what="vendors">
        {(d) => (
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={d.vendors || []} empty="No vendors." cols={[
              { key: "name", label: "Vendor", render: (r) => <b>{r.name}</b> },
              { key: "mode", label: "Mode", render: (r) => <Chip tone={TONE[r.mode] || "bear"}>{r.mode}</Chip> },
            ]} />
          </Card>
        )}
      </AdminLoadable>
    </div>
  );
}
