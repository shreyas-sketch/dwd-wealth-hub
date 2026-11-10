// Admin building blocks (Bullzeye src/bz/admin look): plain table, KPI tile, generic list + add/edit sheet + delete.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button, Card, ErrorCard, Sheet, Skeleton } from "../components/ui";

// Section heading inside an admin page (replaces <Label> caps eyebrows).
export function AdminH({ children, right = null }) {
  return (
    <div className="flex items-baseline justify-between gap-3 mb-3">
      <h2 className="font-bzdisplay text-[20px] font-bold leading-tight">{children}</h2>
      {right}
    </div>
  );
}

export const dt = (v) => {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" });
};

// List payloads may come as an array or as {items: [...]}.
export const asList = (d, key = "items") => (Array.isArray(d) ? d : Array.isArray(d?.[key]) ? d[key] : []);

export function Table({ cols, rows, empty = "Nothing here yet.", onRow }) {
  if (!rows?.length) return <p className="text-sm text-bz-muted py-4">{empty}</p>;
  return (
    <div className="overflow-x-auto -mx-4 sm:mx-0">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-bz-muted">
            {cols.map((c) => <th key={c.key} scope="col" className={`text-[13px] font-semibold px-4 py-2.5 border-b-2 border-bz-line-strong whitespace-nowrap ${c.right ? "text-right" : ""}`}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id || r._id || r.key || r.name || i} onClick={onRow ? () => onRow(r) : undefined}
              className={`border-b border-bz-line last:border-0 hover:bg-bz-inset ${onRow ? "cursor-pointer" : ""}`}>
              {cols.map((c) => <td key={c.key} className={`px-4 py-2.5 align-top ${c.wrap ? "" : "whitespace-nowrap"} ${c.right ? "text-right tabular" : ""}`}>{c.render ? c.render(r) : r[c.key] ?? "—"}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Numbers sit in one surface split by 1px hairlines (the gap shows the line colour), not a card per number.
//   <KpiGrid cols="grid-cols-2 md:grid-cols-4"><Kpi …/>…</KpiGrid>
export function KpiGrid({ cols = "grid-cols-2 md:grid-cols-4", children }) {
  return <div className={`grid ${cols} gap-px bg-bz-line border border-bz-line rounded-bzcard overflow-hidden`}>{children}</div>;
}

export function Kpi({ label, value, sub, tone }) {
  return (
    <div className="bg-bz-card px-4 py-3.5 min-w-0">
      <div className="text-[14px] text-bz-muted truncate">{label}</div>
      <div className={`font-bzdisplay text-[25px] font-bold leading-tight mt-0.5 tabular truncate ${tone === "gold" ? "text-bz-gold-deep" : tone === "up" ? "text-bz-accent" : ""}`}>{value ?? "—"}</div>
      {sub && <div className="text-[13px] text-bz-muted truncate">{sub}</div>}
    </div>
  );
}

export function useAdmin(path, params, opts = {}) {
  return useQuery({ queryKey: ["admin", path, params || null], queryFn: async () => (await api.get(`/admin/${path}`, { params })).data, ...opts });
}

export function AdminLoadable({ q, children, what = "this" }) {
  if (q.isLoading) return <Card><Skeleton lines={5} /></Card>;
  if (q.isError) return <ErrorCard error={q.error} onRetry={() => q.refetch()} what={what} />;
  return children(q.data || {});
}

// Generic CRUD: GET /admin/{path} list, POST /admin/{path}, PUT /admin/{path}/{id}, DELETE /admin/{path}/{id}.
//   Form = ({value, onChange}) => fields;  toBody(value) → request body;  validate(value) → error string | ""
export function CrudPage({ path, title, cols, empty, blank, toForm = (x) => x, toBody = (x) => x, validate = () => "", Form, canDelete = true }) {
  const qc = useQueryClient();
  const q = useAdmin(path);
  const [edit, setEdit] = useState(null);       // {id?, value}
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", path] });

  const save = async () => {
    const v = validate(edit.value);
    if (v) { setErr(v); return; }
    setErr(""); setBusy(true);
    try {
      const body = toBody(edit.value);
      if (edit.id) await api.put(`/admin/${path}/${edit.id}`, body);
      else await api.post(`/admin/${path}`, body);
      setEdit(null); refresh();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  const remove = async (row) => {
    if (!window.confirm(`Delete "${row.name || row.title || row.id}"? This cannot be undone.`)) return;
    try { await api.delete(`/admin/${path}/${row.id}`); refresh(); } catch (e) { window.alert(apiError(e)); }
  };
  const actions = {
    key: "_actions", label: "", render: (r) => (
      <span className="flex gap-1 justify-end">
        <button type="button" className="w-9 h-9 grid place-items-center rounded-bzbtn hover:bg-bz-card" aria-label="Edit" onClick={(e) => { e.stopPropagation(); setErr(""); setEdit({ id: r.id, value: toForm(r) }); }}><Pencil className="w-4 h-4" aria-hidden /></button>
        {canDelete && <button type="button" className="w-9 h-9 grid place-items-center rounded-bzbtn hover:bg-bz-miss-tint text-bz-miss" aria-label="Delete" onClick={(e) => { e.stopPropagation(); remove(r); }}><Trash2 className="w-4 h-4" aria-hidden /></button>}
      </span>
    ),
  };
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="primary" onClick={() => { setErr(""); setEdit({ id: null, value: { ...blank } }); }} data-testid={`admin-add-${path}`}><Plus className="w-4 h-4" aria-hidden /> Add</Button>
      </div>
      <AdminLoadable q={q} what={title}>
        {(d) => <Card className="px-0 sm:px-5 py-2"><Table cols={[...cols, actions]} rows={asList(d)} empty={empty} onRow={(r) => { setErr(""); setEdit({ id: r.id, value: toForm(r) }); }} /></Card>}
      </AdminLoadable>
      <Sheet open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? `Edit ${title}` : `Add ${title}`}>
        {edit && (
          <div className="space-y-4">
            <Form value={edit.value} onChange={(v) => setEdit((e) => ({ ...e, value: v }))} />
            {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
            <div className="flex gap-2">
              <Button className="flex-1" onClick={save} loading={busy} data-testid="admin-save">Save</Button>
              <Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button>
            </div>
          </div>
        )}
      </Sheet>
    </div>
  );
}

export const textareaCls = "w-full rounded-bzbtn border border-bz-line-strong bg-bz-card px-3.5 py-2.5 text-[15px] outline-none focus:border-bz-accent resize-y";
