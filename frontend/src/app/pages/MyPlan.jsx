// /app/plan — My Crypto Plan + Paper Money + My real portfolio.
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Target } from "lucide-react";
import { api, apiError } from "@/lib/api";
import PlanForm from "../components/plan/PlanForm";
import PlanCard from "../components/plan/PlanCard";
import PaperSection from "../components/plan/PaperSection";
import PortfolioSection from "../components/plan/PortfolioSection";
import { Button, Card, Empty, Label, Loadable, PageHeader } from "../components/ui";
import { Gate } from "../components/common";
import { useConfirm } from "../components/Confirm";

function PlanTabs({ plans, sel, setSel }) {
  if (plans.length < 2) return null;
  return (
    <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1" role="tablist" aria-label="Your plans">
      {plans.map((p) => (
        <button key={p.id} type="button" role="tab" aria-selected={sel === p.id} onClick={() => setSel(p.id)}
          className={`shrink-0 min-h-[44px] px-4 rounded-bzbtn text-[14px] font-semibold border ${sel === p.id ? "bg-bz-ink text-bz-bg border-bz-ink" : "bg-bz-inset border-bz-line"}`}>
          {p.goal_name || "Plan"}
        </button>
      ))}
    </div>
  );
}

export default function MyPlan() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: ["plans"], queryFn: async () => (await api.get("/plan")).data });
  const [sel, setSel] = useState(null);
  const [mode, setMode] = useState(null);        // null | "new" | "edit"
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const plans = q.data?.plans || [];
  const max = q.data?.max ?? 1;
  const current = plans.find((p) => p.id === sel) || plans[0] || null;

  const firstId = plans[0]?.id;
  useEffect(() => { if (!sel && firstId) setSel(firstId); }, [firstId, sel]);

  const save = async (body) => {
    setErr(""); setBusy(true);
    try {
      const { data } = mode === "edit" && current ? await api.put(`/plan/${current.id}`, body) : await api.post("/plan", body);
      await qc.invalidateQueries({ queryKey: ["plans"] });
      qc.invalidateQueries({ queryKey: ["coach"] });
      if (data?.id) setSel(data.id);
      setMode(null);
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!current || !(await confirm({ title: "Delete this plan?", danger: true, confirmLabel: "Delete plan",
      body: `"${current.goal_name}" and its projections will be removed. Paper Money started from it keeps its coins.` }))) return;
    try { await api.delete(`/plan/${current.id}`); setSel(null); qc.invalidateQueries({ queryKey: ["plans"] }); }
    catch (e) { setErr(apiError(e)); }
  };

  const header = <PageHeader eyebrow={["My", "_Crypto plan"]} title="Your goal," accent="in rupees." sub="Tell us the goal. We show a simple monthly plan, what it could become in bad, average and good years, and let you practise it with paper money." />;
  return (
    <Gate feature="plan" header={header}>
      <div className="space-y-6">
        {header}
        <Loadable q={q} what="your plans" lines={5}>
          {() => (
            <>
              {mode ? (
                <Card>
                  <Label>{mode === "edit" ? "Edit plan" : "New plan"}</Label>
                  <PlanForm key={mode + (current?.id || "")} initial={mode === "edit" ? current : null} onSubmit={save} busy={busy} error={err}
                    onCancel={plans.length ? () => { setMode(null); setErr(""); } : null} />
                </Card>
              ) : plans.length === 0 ? (
                <Empty icon={Target} title="No plan yet" sub="It takes one minute: a goal, an amount, and how much risk you can take."
                  action={<Button onClick={() => setMode("new")} data-testid="plan-new">Make my plan</Button>} />
              ) : (
                <>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <PlanTabs plans={plans} sel={current?.id} setSel={setSel} />
                    {plans.length < max ? (
                      <Button variant="small" onClick={() => setMode("new")} data-testid="plan-new"><Plus className="w-3.5 h-3.5" aria-hidden /> New plan</Button>
                    ) : <span className="text-[12px] text-bz-muted">{plans.length} of {max} plan{max === 1 ? "" : "s"} on your account</span>}
                  </div>
                  {current && (
                    <PlanCard p={current} actions={<>
                      <Button variant="small" onClick={() => setMode("edit")} data-testid="plan-edit">Edit</Button>
                      <Button variant="small" onClick={remove} className="text-bz-miss" data-testid="plan-delete">Delete</Button>
                    </>} />
                  )}
                  {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
                </>
              )}
            </>
          )}
        </Loadable>

        <section className="space-y-3">
          <div>
            <Label className="mb-1">Paper Money</Label>
            <h2 className="font-bzserif text-[26px] font-semibold leading-tight">Practise <span className="text-bz-accent">before real money.</span></h2>
          </div>
          <PaperSection selectedPlan={current} />
        </section>

        <section className="space-y-3">
          <div>
            <Label className="mb-1">My real portfolio</Label>
            <h2 className="font-bzserif text-[26px] font-semibold leading-tight">What you <span className="text-bz-accent">actually hold.</span></h2>
          </div>
          <PortfolioSection />
        </section>
      </div>
    </Gate>
  );
}
