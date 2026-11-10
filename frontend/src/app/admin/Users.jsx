// Admin › Users: search by phone/name, plan filter, paging; detail sheet with usage + events; grant / trial / revoke.
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { PLAN_LABEL } from "@/lib/features";
import { hdate } from "@/lib/format";
import { Button, Card, Chip, Field, Input, Label, Select, Sheet, Skeleton } from "../components/ui";
import { AdminLoadable, dt, Table, useAdmin } from "./shared";

const PLAN_TONE = { free: "muted", lite: "gold", pro: "solid" };

function Usage({ usage }) {
  if (!usage || typeof usage !== "object") return <p className="text-sm text-bz-muted">No usage yet.</p>;
  const rows = Object.entries(usage).map(([k, v]) => ({ key: k, v }));
  if (!rows.length) return <p className="text-sm text-bz-muted">No usage yet.</p>;
  return (
    <ul className="divide-y divide-bz-line text-[14px]">
      {rows.map(({ key, v }) => (
        <li key={key} className="py-1.5 flex justify-between gap-2">
          <span>{key}</span>
          <span className="tabular text-bz-muted">{v && typeof v === "object" ? `${v.used ?? 0}${v.limit === null ? " / ∞" : v.limit != null ? ` / ${v.limit}` : ""}` : String(v)}</span>
        </li>
      ))}
    </ul>
  );
}

function Detail({ id, onClose }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "user", id], queryFn: async () => (await api.get(`/admin/users/${id}`)).data, enabled: !!id });
  const [grant, setGrant] = useState({ plan: "lite", months: 1 });
  const [days, setDays] = useState(3);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const run = async (kind, path, body) => {
    setMsg(""); setErr(""); setBusy(kind);
    try {
      await api.post(`/admin/users/${id}/${path}`, body);
      setMsg("Saved."); q.refetch(); qc.invalidateQueries({ queryKey: ["admin", "users"] });
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };
  const d = q.data || {};
  const u = d.user || {};
  const p = d.plan || {};
  const revoked = u.status === "revoked";
  return (
    <Sheet open={!!id} onClose={onClose} title={u.name || u.phone || "User"} wide>
      {q.isLoading ? <Skeleton lines={6} /> : q.isError ? <p className="text-sm text-bz-miss">{apiError(q.error)}</p> : (
        <div className="space-y-5" data-testid="admin-user-detail">
          <div className="grid gap-1 text-[14px]">
            <div><span className="text-bz-muted">Phone</span> <b>{u.phone || "—"}</b>{u.email ? <span className="text-bz-muted"> · {u.email}</span> : null}</div>
            <div><span className="text-bz-muted">Joined</span> {dt(u.created_at)} · <span className="text-bz-muted">role</span> {u.role || "user"}{u.status ? <> · <Chip tone={revoked ? "bear" : "bull"}>{u.status}</Chip></> : null}</div>
            <div className="flex items-center gap-2 flex-wrap"><span className="text-bz-muted">Plan</span> <Chip tone={PLAN_TONE[p.plan] || "muted"}>{p.label || PLAN_LABEL[p.plan] || p.plan || "free"}</Chip>
              <span className="text-bz-muted">{p.source}{p.trial_ends_at ? ` · trial to ${hdate(p.trial_ends_at)}` : ""}{p.paid_until ? ` · paid to ${hdate(p.paid_until)}` : ""}</span></div>
          </div>
          <Card inset className="space-y-4">
            <div>
              <Label>Grant a plan</Label>
              <div className="flex flex-wrap gap-2 items-end">
                <Field label="Plan" className="w-40"><Select value={grant.plan} onChange={(e) => setGrant({ ...grant, plan: e.target.value })}>{["lite", "pro", "free"].map((x) => <option key={x} value={x}>{PLAN_LABEL[x]}</option>)}</Select></Field>
                <Field label="Months" className="w-28"><Input type="number" min="1" value={grant.months} onChange={(e) => setGrant({ ...grant, months: Number(e.target.value) })} /></Field>
                <Button onClick={() => run("grant", "grant", grant)} loading={busy === "grant"} data-testid="admin-grant">Grant</Button>
              </div>
            </div>
            <div>
              <Label>Extend trial</Label>
              <div className="flex flex-wrap gap-2 items-end">
                <Field label="Days" className="w-28"><Input type="number" min="1" value={days} onChange={(e) => setDays(Number(e.target.value))} /></Field>
                <Button variant="secondary" onClick={() => run("trial", "trial", { days })} loading={busy === "trial"} data-testid="admin-trial">Extend</Button>
                {p.trial_ends_at && new Date(p.trial_ends_at) > new Date() && (
                  <Button variant="small" onClick={() => run("trial-end", "trial", { days: 0 })} loading={busy === "trial-end"} data-testid="admin-trial-end">End trial now</Button>
                )}
              </div>
              <p className="text-[13px] text-bz-muted mt-1">Ending the trial moves the account to its paid or granted plan, or to Free (useful for testing the Free plan).</p>
            </div>
            <div>
              <Label>Access</Label>
              {revoked ? <Button variant="secondary" onClick={() => run("status", "status", { status: "active" })} loading={busy === "status"}>Restore access</Button>
                : <Button variant="danger" onClick={() => { if (window.confirm("Revoke this account's access?")) run("status", "status", { status: "revoked" }); }} loading={busy === "status"} data-testid="admin-revoke">Revoke access</Button>}
            </div>
            {msg && <p className="text-sm text-bz-accent font-semibold">{msg}</p>}
            {err && <p className="text-sm text-bz-miss">{err}</p>}
          </Card>
          <div className="grid gap-4 md:grid-cols-2">
            <div><Label>Usage this month</Label><Usage usage={d.usage} /></div>
            <div>
              <Label>Recent events</Label>
              {(d.events || []).length ? (
                <ul className="divide-y divide-bz-line text-[13px] max-h-80 overflow-y-auto">
                  {d.events.map((e, i) => (
                    <li key={i} className="py-1.5">
                      <div className="flex justify-between gap-2"><b>{e.name}</b><span className="text-bz-muted">{dt(e.ts)}</span></div>
                      {e.props && Object.keys(e.props).length > 0 && <div className="text-bz-muted font-bzmono text-[11px] break-all">{JSON.stringify(e.props)}</div>}
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-bz-muted">No events.</p>}
            </div>
          </div>
        </div>
      )}
    </Sheet>
  );
}

export default function Users({ initialQ = "" }) {
  const [q, setQ] = useState(initialQ);
  const [term, setTerm] = useState(initialQ);
  const [plan, setPlan] = useState("");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState(null);
  const [pageSize, setPageSize] = useState(0);
  useEffect(() => { const t = setTimeout(() => { setTerm(q.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [q]);
  const list = useAdmin("users", { q: term || undefined, plan: plan || undefined, page });
  const items = list.data?.items || [];
  const total = list.data?.total ?? 0;
  useEffect(() => { if (items.length > pageSize) setPageSize(items.length); }, [items.length, pageSize]);
  const pages = pageSize ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search phone or name" className="sm:max-w-sm" data-testid="admin-user-search" />
        <Select value={plan} onChange={(e) => { setPlan(e.target.value); setPage(1); }} className="sm:w-48" data-testid="admin-user-plan">
          <option value="">All plans</option>
          {["free", "lite", "pro"].map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}
        </Select>
      </div>
      <AdminLoadable q={list} what="users">
        {() => (
          <Card className="px-0 sm:px-5 py-2">
            <p className="text-sm text-bz-muted px-4 sm:px-0 py-2">{Number(total).toLocaleString("en-IN")} {Number(total) === 1 ? "account" : "accounts"}</p>
            <Table rows={items} onRow={(r) => setSel(r.id)} cols={[
              { key: "phone", label: "Phone", render: (r) => <span className="font-semibold text-bz-accent">{r.phone}</span> },
              { key: "name", label: "Name" },
              { key: "plan", label: "Plan", render: (r) => <Chip tone={PLAN_TONE[r.plan] || "muted"}>{PLAN_LABEL[r.plan] || r.plan}</Chip> },
              { key: "source", label: "Source" },
              { key: "created_at", label: "Joined", render: (r) => dt(r.created_at) },
              { key: "last_login_at", label: "Last login", render: (r) => dt(r.last_login_at) },
              { key: "trial_ends_at", label: "Trial to", render: (r) => (r.trial_ends_at ? hdate(r.trial_ends_at) : "—") },
              { key: "paid_until", label: "Paid to", render: (r) => (r.paid_until ? hdate(r.paid_until) : "—") },
              { key: "status", label: "Status", render: (r) => (r.status === "revoked" ? <Chip tone="bear">revoked</Chip> : r.status || "active") },
            ]} empty="No users match." />
            <div className="flex items-center justify-between gap-2 px-4 sm:px-0 py-3">
              <Button variant="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <span className="text-sm text-bz-muted">Page {page} of {pages}</span>
              <Button variant="small" disabled={page >= pages || !items.length} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </Card>
        )}
      </AdminLoadable>
      {sel && <Detail id={sel} onClose={() => setSel(null)} />}
    </div>
  );
}
