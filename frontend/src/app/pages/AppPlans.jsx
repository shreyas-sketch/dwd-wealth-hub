// /app/plans — same as /plans, inside the shell.
import PlansView from "../components/PlansView";
import { PageHeader } from "../components/ui";

export default function AppPlans() {
  return (
    <div>
      <PageHeader eyebrow={["Plans", "_Upgrade"]} title="Pick your" accent="plan." sub="Free, ₹2,000 a month, or ₹5,000 a month for everything." />
      <PlansView inShell />
    </div>
  );
}
