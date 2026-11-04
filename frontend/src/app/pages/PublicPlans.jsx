// /plans — public pricing.
import PublicLayout from "../components/PublicLayout";
import PlansView from "../components/PlansView";
import { PageHeader } from "../components/ui";

export default function PublicPlans() {
  return (
    <PublicLayout>
      <div className="px-4 md:px-8 py-8 sm:py-12 max-w-[980px] mx-auto">
        <PageHeader eyebrow={["Plans", "_Pricing"]} title="Simple plans," accent="in rupees." sub="Start free. Upgrade for the full toolkit. Cancel any time." />
        <PlansView />
      </div>
    </PublicLayout>
  );
}
