// /app/ask — Ask the coach AI: coach card (goal + crash note), thread list, chat with collapsible sources.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BookOpen, MessageCircle, Plus, Send, ShieldAlert } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { ago, inr } from "@/lib/format";
import brand from "@/brand";
import { Button, Card, Chip, Label, Meter, PageHeader, Sheet, Spinner } from "../components/ui";
import { Gate, LockCard, UsageLine } from "../components/common";

const STARTERS = [
  "What is a Bitcoin halving and why does it matter?",
  "How much of my savings should be in crypto?",
  "How do I keep my coins safe on an exchange?",
  "What should I do when the market crashes?",
];

function CoachCard() {
  const q = useQuery({ queryKey: ["coach"], queryFn: async () => (await api.get("/ask/coach", { _silentGate: true })).data });
  const g = q.data?.goal;
  const c = q.data?.crash;
  if (!g && !c?.active) return null;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {g && (
        <Card inset data-testid="coach-goal">
          <Label className="mb-1">Your goal</Label>
          <p className="font-semibold">{g.name}</p>
          <div className="flex justify-between text-[13px] mt-1.5"><span className="tabular">{inr(g.value_inr || 0)} of {inr(g.target_inr)}</span><span className="tabular font-semibold">{Math.round(Number(g.pct) || 0)}%</span></div>
          <Meter value={g.pct} className="mt-1.5" label="Goal progress" />
        </Card>
      )}
      {c?.active && (
        <Card className="border-bz-miss bg-bz-miss-tint" data-testid="coach-crash">
          <div className="flex gap-2.5">
            <AlertTriangle className="w-5 h-5 text-bz-miss shrink-0 mt-0.5" aria-hidden />
            <div>
              <p className="font-semibold">Market drop: Bitcoin {c.drawdown_pct != null ? `−${Math.abs(Number(c.drawdown_pct)).toFixed(0)}%` : "down sharply"}{c.level ? ` (past the ${c.level}% level)` : ""}</p>
              {c.note && <p className="text-[14.5px] mt-1">{c.note}</p>}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <details className="mt-2 group">
      <summary className="cursor-pointer inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-bz-muted py-1 select-none">
        <BookOpen className="w-3.5 h-3.5" aria-hidden /> {sources.length} source{sources.length === 1 ? "" : "s"} from {brand.coach}'s sessions
      </summary>
      <ul className="mt-1.5 space-y-2">
        {sources.map((s, i) => (
          <li key={i} className="rounded-bzbtn border border-bz-line bg-bz-panel px-3 py-2">
            <p className="text-[13px] font-semibold">{s.title}</p>
            {s.snippet && <p className="text-[12.5px] text-bz-muted mt-0.5 line-clamp-3">{s.snippet}</p>}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Bubble({ m }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-[16px] rounded-br-[4px] bg-bz-accent text-bz-on-accent px-4 py-2.5 text-[15.5px] whitespace-pre-wrap">{m.text}</div>
      </div>
    );
  }
  if (m.refused) {
    return (
      <div className="max-w-[92%] rounded-[16px] rounded-bl-[4px] border border-bz-gold bg-bz-gold-tint px-4 py-3" data-testid="ask-refused">
        <div className="flex items-center gap-1.5 font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-gold-deep mb-1"><ShieldAlert className="w-3.5 h-3.5" aria-hidden /> Not a buy / sell call</div>
        <p className="text-[15.5px] whitespace-pre-wrap">{m.text}</p>
        <p className="text-[13px] mt-2">Try <Link to="/app/xray" className="font-semibold text-bz-accent">Coin X-Ray</Link> or today's <Link to="/app/verdicts" className="font-semibold text-bz-accent">Verdicts</Link>.</p>
      </div>
    );
  }
  return (
    <div className="max-w-[92%]">
      <div className="rounded-[16px] rounded-bl-[4px] border border-bz-line bg-bz-card px-4 py-3 text-[15.5px] leading-relaxed whitespace-pre-wrap" data-testid="ask-answer">{m.text}</div>
      <Sources sources={m.sources} />
    </div>
  );
}

function ThreadList({ threads, active, onPick, onNew }) {
  return (
    <div className="space-y-1">
      <Button variant="small" className="w-full mb-2" onClick={onNew} data-testid="ask-new"><Plus className="w-3.5 h-3.5" aria-hidden /> New chat</Button>
      {threads.length === 0 && <p className="text-[13px] text-bz-muted px-1">Your chats appear here.</p>}
      {threads.map((t) => (
        <button key={t.id} type="button" onClick={() => onPick(t.id)} aria-current={active === t.id ? "true" : undefined}
          className={`w-full text-left rounded-bzbtn px-3 py-2.5 min-h-[48px] ${active === t.id ? "bg-bz-inset" : "hover:bg-bz-inset"}`}>
          <span className="block text-[14px] font-medium truncate">{t.title || "Chat"}</span>
          {t.updated_at && <span className="block text-[11.5px] text-bz-muted">{ago(t.updated_at)}</span>}
        </button>
      ))}
    </div>
  );
}

function Chat() {
  const qc = useQueryClient();
  const threads = useQuery({ queryKey: ["ask-threads"], queryFn: async () => (await api.get("/ask/threads", { _silentGate: true })).data });
  const [tid, setTid] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [gate, setGate] = useState(null);
  const [usage, setUsage] = useState(null);
  const [listOpen, setListOpen] = useState(false);
  const [loadingThread, setLoadingThread] = useState(false);
  const endRef = useRef(null);
  const items = threads.data?.items || [];

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  const open = async (id) => {
    setListOpen(false); setErr(""); setGate(null);
    setTid(id); setMsgs([]); setLoadingThread(true);
    try { const { data } = await api.get(`/ask/threads/${id}`); setMsgs(data?.messages || []); }
    catch (e) { setErr(apiError(e)); } finally { setLoadingThread(false); }
  };
  const fresh = () => { setTid(null); setMsgs([]); setErr(""); setGate(null); setListOpen(false); };

  const send = async (q) => {
    const question = (q ?? text).trim();
    if (!question || busy) return;
    setErr(""); setGate(null); setText("");
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const { data } = await api.post("/ask", { question, ...(tid ? { thread_id: tid } : {}) }, { _silentGate: true });
      setMsgs((m) => [...m, { role: "assistant", text: data?.answer || "", sources: data?.sources || [], refused: !!data?.refused }]);
      if (data?.thread_id) setTid(data.thread_id);
      if (data?.usage) setUsage(data.usage);
      qc.invalidateQueries({ queryKey: ["ask-threads"] });
    } catch (e) {
      const d = e?.response?.data?.detail;
      if ((e?.response?.status === 402 || e?.response?.status === 403) && d) setGate(d);
      else setErr(apiError(e));
      setMsgs((m) => m.slice(0, -1));
      setText(question);
    } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[230px_minmax(0,1fr)] items-start">
      <aside className="hidden lg:block rounded-bzcard border border-bz-line bg-bz-panel p-3 sticky top-4 max-h-[70vh] overflow-y-auto">
        <ThreadList threads={items} active={tid} onPick={open} onNew={fresh} />
      </aside>
      <div className="rounded-bzcard border border-bz-line bg-bz-panel flex flex-col min-h-[60vh]">
        <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-bz-line">
          <span className="text-[14px] font-semibold truncate">{tid ? items.find((t) => t.id === tid)?.title || "Chat" : "New chat"}</span>
          <div className="flex gap-2 lg:hidden">
            <Button variant="small" onClick={() => setListOpen(true)} data-testid="ask-threads">Chats</Button>
            <Button variant="small" onClick={fresh}><Plus className="w-3.5 h-3.5" aria-hidden /></Button>
          </div>
        </div>
        <div className="flex-1 px-3 sm:px-4 py-4 space-y-4 overflow-y-auto" aria-live="polite">
          {loadingThread && <Spinner label="Opening chat" />}
          {!loadingThread && msgs.length === 0 && (
            <div className="py-4">
              <MessageCircle className="w-8 h-8 text-bz-gold" strokeWidth={1.6} aria-hidden />
              <p className="font-bzserif text-[22px] font-semibold mt-2">Ask anything about crypto.</p>
              <p className="text-[14.5px] text-bz-muted mt-1">Answers come from {brand.coach}'s own sessions. It won't tell you what to buy or sell; it will help you understand.</p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {STARTERS.map((s) => (
                  <button key={s} type="button" onClick={() => send(s)} className="text-left rounded-bzbtn border border-bz-line bg-bz-card px-3.5 py-3 text-[14px] hover:border-bz-line-strong min-h-[48px]">{s}</button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => <Bubble key={i} m={m} />)}
          {busy && <div className="flex items-center gap-2 text-bz-muted text-[14px]"><span className="flex gap-1" aria-hidden><span className="w-1.5 h-1.5 rounded-full bg-bz-gold animate-bounce" /><span className="w-1.5 h-1.5 rounded-full bg-bz-gold animate-bounce [animation-delay:120ms]" /><span className="w-1.5 h-1.5 rounded-full bg-bz-gold animate-bounce [animation-delay:240ms]" /></span>{brand.coach} AI is thinking</div>}
          {gate && <LockCard feature="ask" planNeeded={gate.plan_needed} kind={gate.code === "limit" ? "limit" : "locked"} used={gate.used} limit={gate.limit} msg={gate.msg} />}
          {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
          <div ref={endRef} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(); }} className="border-t border-bz-line p-3 flex gap-2 items-end bg-bz-card rounded-b-bzcard">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} placeholder="Type your question" data-testid="ask-input"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            className="flex-1 min-h-[48px] max-h-40 resize-y rounded-bzbtn border border-bz-line-strong bg-bz-card px-3.5 py-3 text-[16px] outline-none focus:border-bz-accent" />
          <Button type="submit" className="!px-4" disabled={!text.trim() || busy} aria-label="Send" data-testid="ask-send"><Send className="w-4 h-4" aria-hidden /></Button>
        </form>
      </div>
      {usage && <UsageLine usage={usage} what="questions" className="lg:col-start-2" />}
      <Sheet open={listOpen} onClose={() => setListOpen(false)} title="Your chats">
        <ThreadList threads={items} active={tid} onPick={open} onNew={fresh} />
      </Sheet>
    </div>
  );
}

export default function Ask() {
  const header = <PageHeader eyebrow={["Ask", `_${brand.coach} AI`]} title="Your crypto teacher," accent="any time." sub={`Ask in your own words. Answers are in ${brand.coach}'s teaching style, from his sessions, with the sources shown.`} right={<Chip tone="gold">₹5,000 plan</Chip>} />;
  return (
    <Gate feature="ask" header={header}>
      <div className="space-y-4">
        {header}
        <CoachCard />
        <Chat />
        <p className="text-[12px] text-bz-muted">AI answers can be wrong. This is education, not investment advice.</p>
      </div>
    </Gate>
  );
}
