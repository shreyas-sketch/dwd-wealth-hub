// Small primitives in Bullzeye's look: 16px cards, JetBrains Mono labels and buttons,
// Fraunces headlines with one accented phrase, light + dark through the --bz-* tokens.
import { Link } from "react-router-dom";
import { AlertTriangle, Loader2, RotateCw } from "lucide-react";
import { apiError } from "@/lib/api";

export function Card({ className = "", inset = false, children, ...rest }) {
  return (
    <section
      className={`rounded-bzcard p-5 ${inset ? "bg-bz-inset border border-bz-line" : "bg-bz-card border border-bz-line shadow-bzframe"} ${className}`}
      {...rest}
    >
      {children}
    </section>
  );
}

export function Label({ children, className = "", tone = "muted", as: As = "div" }) {
  const color = { muted: "text-bz-muted", bull: "text-bz-accent", bear: "text-bz-miss", gold: "text-bz-gold-deep" }[tone];
  return <As className={`font-bzmono text-[11px] uppercase tracking-[0.2em] ${color} mb-2.5 ${className}`}>{children}</As>;
}

// Mono eyebrow with a square dot, Fraunces headline with one accented phrase.
//   <PageHeader eyebrow={["Coin", "_X-Ray"]} title="Is it safe," accent="or a scam?" />
export function PageHeader({ eyebrow, title, accent, accentTone = "bull", sub, right = null }) {
  const [lead, rest] = Array.isArray(eyebrow) ? eyebrow : [eyebrow, ""];
  const tone = accentTone === "gold" ? "text-bz-gold" : "text-bz-accent";
  return (
    <header className="mb-6 md:mb-8">
      <div className="flex items-center justify-between gap-4">
        {eyebrow ? (
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 rounded-[3px] bg-bz-gold" aria-hidden />
            <span className="font-bzmono text-[11px] tracking-[0.28em] uppercase">
              <span className="text-bz-gold-deep">{lead}</span>
              <span className="text-bz-muted">{rest}</span>
            </span>
          </div>
        ) : <span />}
        {right}
      </div>
      {title ? (
        <h1 className="font-bzserif mt-5 text-[32px] sm:text-[42px] lg:text-[48px] font-semibold leading-[1.06] tracking-[-0.01em]">
          {title}{accent ? <> <span className={tone}>{accent}</span></> : null}
        </h1>
      ) : null}
      {sub ? <p className="mt-3 text-[16px] leading-relaxed text-bz-muted max-w-[640px]">{sub}</p> : null}
    </header>
  );
}

const BTN_BASE =
  "inline-flex items-center justify-center gap-2 rounded-bzbtn transition-colors disabled:opacity-60 disabled:cursor-not-allowed select-none";
const BTN_BOXED = "min-h-[48px] px-5 py-3 border font-bzmono text-[12px] uppercase tracking-[0.16em] text-center";
const BTN_STYLES = {
  primary: `${BTN_BOXED} bg-bz-accent text-bz-on-accent border-bz-accent hover:opacity-90`,
  secondary: `${BTN_BOXED} bg-transparent text-bz-ink border-bz-line-strong hover:bg-bz-inset`,
  quiet: `${BTN_BOXED} bg-bz-inset text-bz-ink border-bz-line hover:border-bz-line-strong`,
  danger: `${BTN_BOXED} bg-transparent text-bz-miss border-bz-miss hover:bg-bz-miss-tint`,
  gold: `${BTN_BOXED} bg-bz-gold text-white border-bz-gold hover:opacity-90`,
  small: "min-h-[36px] px-3 py-1.5 border border-bz-line bg-bz-card font-bzmono text-[11px] uppercase tracking-[0.14em] hover:bg-bz-inset",
  link: "bg-transparent text-bz-accent font-semibold text-[15px] px-0 py-1",
};

export function Button({ variant = "primary", loading = false, className = "", children, type = "button", ...rest }) {
  return (
    <button type={type} className={`${BTN_BASE} ${BTN_STYLES[variant]} ${className}`} disabled={loading || rest.disabled} {...rest}>
      {loading && <Loader2 className="w-4 h-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function LinkButton({ to, variant = "primary", className = "", children, ...rest }) {
  return <Link to={to} className={`${BTN_BASE} ${BTN_STYLES[variant]} ${className}`} {...rest}>{children}</Link>;
}

export function Spinner({ label = "Loading" }) {
  return (
    <div className="flex items-center gap-2 text-bz-muted text-sm py-6 justify-center" role="status">
      <Loader2 className="w-4 h-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function Skeleton({ lines = 3, className = "" }) {
  return (
    <div className={`space-y-3 ${className}`} aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton h-5" style={{ width: `${100 - (i % 3) * 18}%` }} />
      ))}
    </div>
  );
}

export function SkeletonCard({ lines = 3 }) {
  return <Card><Skeleton lines={lines} /></Card>;
}

export function ErrorCard({ error, onRetry, what = "this" }) {
  return (
    <Card inset className="flex items-start gap-3" role="alert">
      <AlertTriangle className="w-5 h-5 text-bz-miss shrink-0 mt-0.5" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">Could not load {what}.</p>
        <p className="text-sm text-bz-muted mt-0.5">{apiError(error)}</p>
        {onRetry && (
          <button type="button" onClick={onRetry} className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-bz-accent">
            <RotateCw className="w-3.5 h-3.5" aria-hidden /> Try again
          </button>
        )}
      </div>
    </Card>
  );
}

export function Empty({ title, sub, action = null, icon: Icon }) {
  return (
    <Card inset className="text-center py-8">
      {Icon && <Icon className="w-7 h-7 mx-auto text-bz-gold mb-2" strokeWidth={1.6} aria-hidden />}
      <p className="font-semibold text-[16px]">{title}</p>
      {sub && <p className="text-sm text-bz-muted mt-1 max-w-[420px] mx-auto">{sub}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </Card>
  );
}

// Render a react-query result: skeleton while loading, error card with retry, then children(data).
export function Loadable({ q, what, lines = 3, children }) {
  if (q.isLoading) return <SkeletonCard lines={lines} />;
  if (q.isError) return <ErrorCard error={q.error} onRetry={() => q.refetch()} what={what} />;
  return children(q.data || {});
}

export function Sheet({ open, onClose, title, children, wide = false }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="absolute inset-0 bg-bz-scrim cursor-default" aria-label="Close" onClick={onClose} />
      <div className={`relative w-full ${wide ? "sm:max-w-[820px]" : "sm:max-w-[620px]"} max-h-[92vh] overflow-y-auto bg-bz-card rounded-t-[16px] sm:rounded-bzcard border border-bz-line shadow-bzsheet pb-[env(safe-area-inset-bottom)]`}>
        <div className="sticky top-0 z-10 bg-bz-card flex items-center justify-between px-5 pt-4 pb-3 border-b border-bz-line">
          <h2 className="font-bzserif text-[20px] font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="font-bzmono text-[11px] uppercase tracking-[0.2em] text-bz-muted px-2 py-2 rounded-bzbtn hover:bg-bz-inset">Close</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

const CHIP_TONES = {
  muted: "bg-bz-inset text-bz-muted",
  right: "bg-bz-accent-tint text-bz-accent",
  bull: "bg-bz-accent-tint text-bz-accent",
  miss: "bg-bz-miss-tint text-bz-miss",
  bear: "bg-bz-miss-tint text-bz-miss",
  gold: "bg-bz-gold-tint text-bz-gold-deep",
  solid: "bg-bz-gold text-white",
};
export function Chip({ tone = "muted", children, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-1 font-bzmono text-[11px] uppercase tracking-[0.08em] px-2 py-0.5 rounded-md whitespace-nowrap ${CHIP_TONES[tone] || CHIP_TONES.muted} ${className}`}>
      {children}
    </span>
  );
}

// Collapsible section: details stay one tap away.
export function Section({ title, meta, defaultOpen = false, children, id }) {
  return (
    <details id={id} open={defaultOpen} className="group border-b border-bz-line">
      <summary className="list-none cursor-pointer flex items-center justify-between gap-3 py-4 select-none">
        <span className="text-[15px] font-semibold">{title}</span>
        <span className="flex items-center gap-2 min-w-0 text-[13px] text-bz-muted">
          <span className="truncate">{meta}</span>
          <svg className="w-4 h-4 shrink-0 transition-transform group-open:rotate-90" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M9 6l6 6-6 6" /></svg>
        </span>
      </summary>
      <div className="pb-5">{children}</div>
    </details>
  );
}

// One tappable row: title, one-line subtitle, something on the right.
export function RowLink({ to, href, onClick, title, sub, right, testid }) {
  const inner = (
    <>
      <span className="flex flex-col gap-0.5 min-w-0">
        <span className="text-[15px] font-semibold truncate">{title}</span>
        {sub && <span className="text-[13px] text-bz-muted truncate">{sub}</span>}
      </span>
      {right ?? <svg className="w-5 h-5 text-bz-muted shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M9 6l6 6-6 6" /></svg>}
    </>
  );
  const cls = "w-full flex items-center justify-between gap-3 py-3.5 border-b border-bz-line text-left text-bz-ink hover:bg-bz-inset min-h-[52px]";
  if (to) return <Link to={to} className={cls} data-testid={testid}>{inner}</Link>;
  if (href) return <a href={href} className={cls} data-testid={testid}>{inner}</a>;
  return <button type="button" onClick={onClick} className={cls} data-testid={testid}>{inner}</button>;
}

// ---- form controls -------------------------------------------------------
export const inputCls =
  "w-full min-h-[48px] rounded-bzbtn border border-bz-line-strong bg-bz-card text-bz-ink px-3.5 py-2.5 text-[16px] " +
  "placeholder:text-bz-muted outline-none focus:border-bz-accent";

export function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="block font-bzmono text-[11px] uppercase tracking-[0.16em] text-bz-muted mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-[12px] text-bz-muted mt-1">{hint}</span>}
    </label>
  );
}

export function Input({ className = "", ...rest }) {
  return <input className={`${inputCls} ${className}`} {...rest} />;
}

// Rupee amount input with a ₹ prefix.
// `min`/`max` props are dropped on purpose: the browser would block the form without a visible message on a phone;
// screens check the amount themselves and the API answers with a plain sentence.
export function MoneyInput({ value, onChange, className = "", min: _min, max: _max, ...rest }) {
  return (
    <div className={`relative ${className}`}>
      <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-bz-muted text-[16px]" aria-hidden>₹</span>
      <input type="number" inputMode="decimal" min="0" step="any" value={value} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        className={`${inputCls} pl-8 tabular`} {...rest} />
    </div>
  );
}

export function Select({ className = "", children, ...rest }) {
  return <select className={`${inputCls} ${className}`} {...rest}>{children}</select>;
}

// Row of big option buttons (coin, years, risk…).
export function Segmented({ options, value, onChange, label, testid, className = "" }) {
  return (
    <div className={`flex gap-1.5 ${className}`} role="group" aria-label={label}>
      {options.map((o) => {
        const v = typeof o === "object" ? o.value : o;
        const l = typeof o === "object" ? o.label : o;
        const on = value === v;
        return (
          <button key={String(v)} type="button" onClick={() => onChange(v)} aria-pressed={on}
            data-testid={testid ? `${testid}-${v}` : undefined}
            className={`flex-1 min-h-[44px] px-2 rounded-bzbtn font-bzmono text-[12px] tracking-[0.1em] uppercase border ${on ? "bg-bz-ink text-bz-bg border-bz-ink" : "bg-bz-inset text-bz-ink border-bz-line hover:border-bz-line-strong"}`}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

// Thin horizontal meter 0–100.
export function Meter({ value = 0, tone = "accent", className = "", label }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const bg = { accent: "bg-bz-accent", miss: "bg-bz-miss", gold: "bg-bz-gold" }[tone] || "bg-bz-accent";
  return (
    <div className={`h-2.5 rounded-full bg-bz-inset overflow-hidden ${className}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={v} aria-label={label}>
      <div className={`h-full rounded-full ${bg}`} style={{ width: `${v}%` }} />
    </div>
  );
}

export function Stat({ label, value, sub, tone }) {
  const c = tone === "up" ? "text-bz-accent" : tone === "down" ? "text-bz-miss" : "";
  return (
    <div className="rounded-bzbtn border border-bz-line bg-bz-card px-3.5 py-3 min-w-0">
      <div className="font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-muted truncate">{label}</div>
      <div className={`text-[20px] font-semibold mt-1 tabular truncate ${c}`}>{value}</div>
      {sub && <div className="text-[12px] text-bz-muted mt-0.5 truncate">{sub}</div>}
    </div>
  );
}

export function Disclaimer({ text, className = "" }) {
  if (!text) return null;
  return <p className={`text-[12px] leading-relaxed text-bz-muted ${className}`}>{text}</p>;
}

export function ErrorLine({ children }) {
  if (!children) return null;
  return <p className="text-sm text-bz-miss mt-2" role="alert">{children}</p>;
}

export function OkLine({ children }) {
  if (!children) return null;
  return <p className="text-sm text-bz-accent font-semibold mt-2" role="status">{children}</p>;
}
