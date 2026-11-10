// /app/account — profile (name, email), plan details, usage meters, cancel subscription, theme, log out.
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ThemeToggle, useTheme } from "@/context/ThemeContext";
import { daysUntil, hdate } from "@/lib/format";
import { PLAN_LABEL } from "@/lib/features";
import brand from "@/brand";
import { Button, Card, Field, Input, Label, LinkButton, Meter, OkLine, PageHeader } from "../components/ui";
import { PlanChip } from "../components/common";
import { useConfirm } from "../components/Confirm";

const USAGE_NAME = { xray: "Coin X-Ray checks", forecast: "Forecasts", debate: "Debates", chart: "Chart reads", ask: `Questions to ${brand.coach} AI` };
const SOURCE = { trial: "Free trial", paid: "Paid subscription", grant: "Given by our team", free: "Free" };

function Profile() {
  const { user, setUser } = useAuth();
  const [f, setF] = useState({ name: user?.name || "", email: user?.email || "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  useEffect(() => { setF({ name: user?.name || "", email: user?.email || "" }); }, [user?.name, user?.email]);
  const save = async (e) => {
    e.preventDefault();
    setErr(""); setOk("");
    if (f.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) { setErr("That email doesn't look right."); return; }
    setBusy(true);
    try {
      const { data } = await api.patch("/auth/profile", { name: f.name.trim(), email: f.email.trim() || null });
      if (data?.user) setUser(data.user);
      setOk("Saved.");
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <Card>
      <Label>Profile</Label>
      <form onSubmit={save} noValidate className="space-y-3">
        <Field label="Mobile"><Input value={user?.phone || ""} disabled readOnly className="opacity-70" /></Field>
        <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" maxLength={60} data-testid="profile-name" /></Field>
        <Field label="Email (optional)" hint="For receipts and important account notes."><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" data-testid="profile-email" /></Field>
        {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
        <OkLine>{ok}</OkLine>
        <Button type="submit" loading={busy} data-testid="profile-save">Save</Button>
      </form>
    </Card>
  );
}

function PlanDetails() {
  const { plan, refreshMe } = useAuth();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const p = plan || {};
  const trialLeft = p.source === "trial" ? daysUntil(p.trial_ends_at) : null;
  const cancel = async () => {
    if (!(await confirm({ title: "Cancel your subscription?", danger: true, confirmLabel: "Cancel subscription", cancelLabel: "Keep my plan",
      body: "You keep your plan until the end of the month you paid for. After that your account moves to the free plan." }))) return;
    setErr(""); setMsg(""); setBusy(true);
    try {
      const { data } = await api.post("/billing/cancel");
      const until = data?.access_until ? hdate(data.access_until) : null;
      setMsg(`Cancelled. You keep the ${p.label || "plan"}${until ? ` until ${until}` : " to the end of the paid month"} and won't be charged again.`);
      refreshMe();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  const limits = Object.entries(p.limits || {});
  return (
    <Card>
      <Label>Your plan</Label>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-bzserif text-[24px] font-semibold">{p.label || PLAN_LABEL[p.plan] || "Free"}</span>
        <PlanChip plan={p} />
      </div>
      <p className="text-[14.5px] text-bz-muted mt-1">
        {SOURCE[p.source] || ""}
        {trialLeft != null ? ` · ends in ${trialLeft} day${trialLeft === 1 ? "" : "s"} (${hdate(p.trial_ends_at)})` : ""}
        {p.paid_until ? (p.cancelling ? ` · cancelled, ends ${hdate(p.paid_until)}` : ` · renews ${hdate(p.paid_until)}`) : ""}
      </p>
      {limits.length > 0 && (
        <div className="mt-5 space-y-3" data-testid="usage-meters">
          <Label className="mb-0">This month's usage</Label>
          {limits.map(([k, u]) => {
            const used = Number(u?.used) || 0;
            const lim = u?.limit;
            const none = lim === 0;
            return (
              <div key={k}>
                <div className="flex justify-between text-[14px]">
                  <span>{USAGE_NAME[k] || k}</span>
                  <span className="tabular text-bz-muted">{none ? "Not on your plan" : lim == null ? `${used} · unlimited` : `${used} of ${lim}`}</span>
                </div>
                {!none && lim != null && <Meter value={(used / lim) * 100} tone={used >= lim ? "miss" : "accent"} className="mt-1" label={USAGE_NAME[k] || k} />}
              </div>
            );
          })}
        </div>
      )}
      <div className="mt-5 flex flex-col sm:flex-row gap-2">
        <LinkButton to="/app/plans" className="sm:flex-1">{p.plan === "pro" && p.source === "paid" ? "See plans" : "Upgrade"}</LinkButton>
        {p.source === "paid" && !p.cancelling && <Button variant="danger" onClick={cancel} loading={busy} data-testid="billing-cancel">Cancel subscription</Button>}
      </div>
      <OkLine>{msg}</OkLine>
      {err && <p className="text-sm text-bz-miss mt-2" role="alert">{err}</p>}
    </Card>
  );
}

export default function Account() {
  const { logout, user } = useAuth();
  const { theme } = useTheme();
  const nav = useNavigate();
  return (
    <div className="space-y-4">
      <PageHeader eyebrow={["Your", "_Account"]} title="Your" accent="account." />
      <div className="grid gap-4 md:grid-cols-2 items-start">
        <PlanDetails />
        <Profile />
      </div>
      <Card>
        <Label>Look</Label>
        <div className="flex items-center justify-between gap-3">
          <span className="text-[15px]">{theme === "dark" ? "Dark mode" : "Light mode"}</span>
          <ThemeToggle />
        </div>
      </Card>
      {user?.role === "admin" && <Link to="/admin" className="block text-[15px] font-semibold text-bz-accent">Open the admin panel</Link>}
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-[14px]">
        <Link to="/terms" className="text-bz-muted hover:text-bz-ink">Terms</Link>
        <Link to="/privacy" className="text-bz-muted hover:text-bz-ink">Privacy</Link>
        <Link to="/disclosures" className="text-bz-muted hover:text-bz-ink">Risk disclosures</Link>
      </div>
      <Button variant="secondary" className="w-full sm:w-auto" data-testid="account-logout" onClick={async () => { await logout(); nav("/login", { replace: true }); }}>Log out</Button>
    </div>
  );
}
