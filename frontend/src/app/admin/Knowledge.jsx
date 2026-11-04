// Admin › Knowledge base for the AI coach: upload .txt / .vtt / .md with a title; list; delete.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2, Upload } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button, Card, Field, Input, Label, OkLine } from "../components/ui";
import { AdminLoadable, asList, dt, Table, useAdmin } from "./shared";

export default function AdminKnowledge() {
  const qc = useQueryClient();
  const q = useAdmin("kb");
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const upload = async (e) => {
    e.preventDefault();
    if (!file) return;
    setErr(""); setOk(""); setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title.trim() || file.name.replace(/\.(txt|vtt|md)$/i, ""));
      await api.post("/admin/kb", fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 });
      setOk(`Added "${title.trim() || file.name}".`); setFile(null); setTitle("");
      e.target.reset();
      qc.invalidateQueries({ queryKey: ["admin", "kb"] });
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete "${r.title}" from the knowledge base?`)) return;
    try { await api.delete(`/admin/kb/${r.id}`); qc.invalidateQueries({ queryKey: ["admin", "kb"] }); } catch (e) { window.alert(apiError(e)); }
  };
  return (
    <div className="space-y-4">
      <Card>
        <Label>Add a document</Label>
        <form onSubmit={upload} className="space-y-3">
          <Field label="File" hint=".txt, .vtt (Zoom transcript) or .md. Timecodes are removed automatically.">
            <input type="file" accept=".txt,.vtt,.md,text/plain,text/markdown,text/vtt" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="kb-file"
              className="block w-full text-[14px] file:mr-3 file:min-h-[44px] file:px-4 file:rounded-bzbtn file:border file:border-bz-line file:bg-bz-inset file:text-bz-ink file:font-semibold" />
          </Field>
          <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Bootcamp Day 2 – Bitcoin cycles" data-testid="kb-title" /></Field>
          {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
          <OkLine>{ok}</OkLine>
          <Button type="submit" loading={busy} disabled={!file} data-testid="kb-upload"><Upload className="w-4 h-4" aria-hidden /> Upload</Button>
        </form>
      </Card>
      <AdminLoadable q={q} what="the knowledge base">
        {(d) => (
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={asList(d)} empty="No documents yet. The coach answers only from what you upload here." cols={[
              { key: "title", label: "Title", wrap: true, render: (r) => <b>{r.title}</b> },
              { key: "chunks", label: "Chunks", right: true },
              { key: "words", label: "Words", right: true, render: (r) => Number(r.words || 0).toLocaleString("en-IN") },
              { key: "uploaded_at", label: "Uploaded", render: (r) => dt(r.uploaded_at) },
              { key: "_del", label: "", render: (r) => <button type="button" aria-label="Delete" onClick={() => remove(r)} className="w-9 h-9 grid place-items-center rounded-bzbtn hover:bg-bz-miss-tint text-bz-miss"><Trash2 className="w-4 h-4" /></button> },
            ]} />
          </Card>
        )}
      </AdminLoadable>
    </div>
  );
}
