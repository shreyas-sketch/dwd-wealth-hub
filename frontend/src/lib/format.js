// Formatting helpers: rupees en-IN (₹1,00,000), dollars, percentages, dates.

const num = (v) => (v === null || v === undefined || v === "" || Number.isNaN(Number(v)) ? null : Number(v));

export function inr(v, decimals = 0) {
  const n = num(v);
  if (n === null) return "—";
  return `${n < 0 ? "−" : ""}₹${Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

const trimZeros = (t) => (t.includes(".") ? t.replace(/0+$/, "").replace(/\.$/, "") : t);

// ₹12.4 L / ₹1.2 Cr for chart axes and tight tiles.
export function inrShort(v) {
  const n = num(v);
  if (n === null) return "—";
  const a = Math.abs(n);
  const s = n < 0 ? "−" : "";
  if (a >= 1e7) return `${s}₹${trimZeros((a / 1e7).toFixed(a >= 1e9 ? 0 : 2))} Cr`;
  if (a >= 1e5) return `${s}₹${trimZeros((a / 1e5).toFixed(1))} L`;
  if (a >= 1e3) return `${s}₹${(a / 1e3).toFixed(0)}K`;
  return `${s}₹${a.toFixed(0)}`;
}

export function usd(v) {
  const n = num(v);
  if (n === null) return "—";
  const a = Math.abs(n);
  const d = a >= 1000 ? 0 : a >= 1 ? 2 : a >= 0.01 ? 4 : 8;
  return `${n < 0 ? "−" : ""}$${a.toLocaleString("en-US", { minimumFractionDigits: Math.min(d, 2), maximumFractionDigits: d })}`;
}

export function usdShort(v) {
  const n = num(v);
  if (n === null) return "—";
  const a = Math.abs(n);
  if (a >= 1e12) return `$${(a / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(a / 1e3).toFixed(0)}K`;
  return usd(n);
}

export function pct(v, decimals = 1, signed = true) {
  const n = num(v);
  if (n === null) return "—";
  return `${signed && n > 0 ? "+" : ""}${n < 0 ? "−" : ""}${Math.abs(n).toFixed(decimals)}%`;
}

export const sign = (v) => (num(v) === null ? 0 : Math.sign(Number(v)));

function toDate(iso) {
  if (!iso) return null;
  const s = String(iso);
  // Date-only values ("2026-11-03") are calendar days: kept at UTC midnight and shown in UTC so they never shift.
  // Timestamps are shown in India time whatever the phone's time-zone setting is.
  const d = s.length <= 10 ? new Date(`${s}T00:00:00Z`) : new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

const IST = "Asia/Kolkata";
const tzOf = (iso) => (String(iso).length <= 10 ? "UTC" : IST);

// Today's date in India, "YYYY-MM-DD".
export function istToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST }).format(new Date());
}

// Hour of the day in India (0–23).
export function istHour() {
  return Number(new Intl.DateTimeFormat("en-GB", { timeZone: IST, hour: "numeric", hourCycle: "h23" }).format(new Date()));
}

// "3 Nov 2026"
export function hdate(iso) {
  const d = toDate(iso);
  return d ? d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: tzOf(iso) }) : "";
}

// "3 Nov" (year only when not this year)
export function sdate(iso) {
  const d = toDate(iso);
  if (!d) return "";
  const tz = tzOf(iso);
  const same = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric" }).format(d) === istToday().slice(0, 4);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: tz, ...(same ? {} : { year: "numeric" }) });
}

// "3 Nov, 10:30 am"
export function dtime(iso) {
  const d = toDate(iso);
  return d ? d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: tzOf(iso) }) : "";
}

// "5 min ago", "3 h ago", "2 days ago"
export function ago(iso) {
  const d = toDate(iso);
  if (!d) return "";
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} day${s < 172800 ? "" : "s"} ago`;
  return sdate(iso);
}

// "2021-11" → "Nov 2021"
export function monthLabel(ym) {
  if (!ym) return "";
  const d = toDate(`${String(ym).slice(0, 7)}-01`);
  return d ? d.toLocaleDateString("en-IN", { month: "short", year: "numeric", timeZone: "UTC" }) : String(ym);
}

export function daysUntil(iso) {
  const d = toDate(iso);
  if (!d) return null;
  if (String(iso).length <= 10) return Math.max(0, Math.round((d.getTime() - new Date(`${istToday()}T00:00:00Z`).getTime()) / 86400000));
  return Math.max(0, Math.ceil((d.getTime() - Date.now()) / 86400000));
}

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const VENUE_NAME = { kucoin: "KuCoin", binance: "Binance" };
export const venueName = (v) => (v ? String(v).split(" · ").map((x) => VENUE_NAME[x] || x).join(" · ") : "—");
