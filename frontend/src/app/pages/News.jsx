// /app/news — News Decoder: feed (Yours first), plain summary, what it means for you, sentiment; "Real or hype?" checker.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Newspaper } from "lucide-react";
import { useFeature } from "@/context/AuthContext";
import { api, apiError } from "@/lib/api";
import { ago } from "@/lib/format";
import { Button, Card, Chip, Empty, Label, Loadable, PageHeader } from "../components/ui";
import { Gate } from "../components/common";

const SENT = { positive: { label: "Good news", tone: "bull" }, negative: { label: "Bad news", tone: "bear" }, neutral: { label: "Neutral", tone: "muted" } };
const CHECK = { real: { label: "Looks real", tone: "bull", cls: "border-bz-accent" }, hype: { label: "Looks like hype", tone: "bear", cls: "border-bz-miss" }, unclear: { label: "Unclear", tone: "gold", cls: "border-bz-gold" } };

function Checker() {
  const [text, setText] = useState("");
  const [s, setS] = useState({ status: "idle" });
  const go = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setS({ status: "loading" });
    try { setS({ status: "done", data: (await api.post("/news/check", { text: text.trim() })).data || {} }); }
    catch (e2) { setS({ status: "error", msg: apiError(e2) }); }
  };
  const r = s.data;
  const c = r && (CHECK[r.verdict] || CHECK.unclear);
  return (
    <Card>
      <Label>Real or hype?</Label>
      <form onSubmit={go} className="space-y-2.5">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} data-testid="news-check-input"
          placeholder="Paste a news link or a forwarded message, e.g. &quot;Government to ban Bitcoin from next month&quot;"
          className="w-full rounded-bzbtn border border-bz-line-strong bg-bz-card px-3.5 py-3 text-[16px] outline-none focus:border-bz-accent resize-y min-h-[88px]" />
        <Button type="submit" className="w-full" loading={s.status === "loading"} disabled={!text.trim()} data-testid="news-check-submit">Check it</Button>
      </form>
      {s.status === "error" && <p className="text-sm text-bz-miss mt-2" role="alert">{s.msg}</p>}
      {s.status === "done" && (
        <div className={`mt-4 rounded-bzcard border-2 ${c.cls} p-4 rise-in`} data-testid="news-check-result">
          <Chip tone={c.tone}>{c.label}</Chip>
          {r.summary && <p className="text-[15.5px] mt-2">{r.summary}</p>}
          {(r.reasons || []).length > 0 && <ul className="mt-2 space-y-1 text-[14px] list-disc pl-5">{r.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>}
        </div>
      )}
    </Card>
  );
}

function Item({ n }) {
  const s = SENT[n.sentiment] || SENT.neutral;
  return (
    <Card className={`p-4 sm:p-5 ${n.yours ? "border-bz-gold" : ""}`} data-testid={`news-${n.id}`}>
      <div className="flex items-center gap-1.5 flex-wrap">
        <Chip tone={s.tone}>{s.label}</Chip>
        {n.yours && <Chip tone="solid">Yours</Chip>}
        {(n.coins || []).map((c) => <Chip key={c} tone="gold">{c}</Chip>)}
      </div>
      <h3 className="text-[17px] font-semibold leading-snug mt-2">{n.title}</h3>
      <p className="text-[12.5px] text-bz-muted mt-0.5">{[n.source, n.published_at && ago(n.published_at)].filter(Boolean).join(" · ")}</p>
      {n.summary && <p className="text-[15px] mt-2.5">{n.summary}</p>}
      {n.what_it_means && (
        <div className="mt-3 rounded-bzbtn bg-bz-inset px-3.5 py-2.5">
          <div className="font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-gold-deep">What it means for you</div>
          <p className="text-[14.5px] mt-1">{n.what_it_means}</p>
        </div>
      )}
      {n.url && <a href={n.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-[13px] font-semibold text-bz-accent min-h-[40px]">Read the full story <ExternalLink className="w-3.5 h-3.5" aria-hidden /></a>}
    </Card>
  );
}

export default function News() {
  const can = useFeature("news");
  const q = useQuery({ queryKey: ["news"], queryFn: async () => (await api.get("/news")).data, enabled: can });
  const [yoursFirst, setYoursFirst] = useState(true);
  const header = <PageHeader eyebrow={["News", "_Decoder"]} title="Crypto news," accent="in plain words." sub="What happened, and what it means for someone like you. News about coins you follow is marked Yours." />;
  return (
    <Gate feature="news" header={header}>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] items-start">
        <div className="space-y-3 lg:col-span-2">{header}</div>
        <div className="space-y-3 order-2 lg:order-1">
          <div className="flex items-center justify-between gap-2">
            <Label className="mb-0">Latest</Label>
            <label className="inline-flex items-center gap-2 text-[14px] font-medium cursor-pointer min-h-[40px]">
              <input type="checkbox" checked={yoursFirst} onChange={(e) => setYoursFirst(e.target.checked)} className="w-5 h-5 accent-[var(--bz-gold)]" data-testid="news-yours-first" />
              Yours first
            </label>
          </div>
          <Loadable q={q} what="the news" lines={6}>
            {(d) => {
              let items = (d.items || []).slice().sort((a, b) => String(b.published_at || "").localeCompare(String(a.published_at || "")));
              if (yoursFirst) items = [...items.filter((n) => n.yours), ...items.filter((n) => !n.yours)];
              return items.length ? <div className="space-y-3">{items.map((n) => <Item key={n.id || n.title} n={n} />)}</div>
                : <Empty icon={Newspaper} title="No news yet" sub="We read the main crypto news sites every two hours." />;
            }}
          </Loadable>
        </div>
        <div className="order-1 lg:order-2 lg:sticky lg:top-4"><Checker /></div>
      </div>
    </Gate>
  );
}
