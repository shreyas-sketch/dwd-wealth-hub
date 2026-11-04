// Axios instance for the Coinzeye API (docs/API_CONTRACT.md).
// Same origin in production; set REACT_APP_BACKEND_URL only when the API lives on another host.
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API_BASE, withCredentials: true });

// ---- Session renewal: on 401 call POST /auth/refresh once (shared by requests failing together), then retry.
const NO_RENEW = ["/auth/refresh", "/auth/session", "/auth/logout", "/auth/otp/", "/auth/staff/login", "/qa/login"];
let renewing = null;
function renewSession() {
  if (!renewing) {
    renewing = axios
      .post(`${API_BASE}/auth/refresh`, null, { withCredentials: true })
      .finally(() => { setTimeout(() => { renewing = null; }, 0); });
  }
  return renewing;
}

// ---- Gate events: 402 limit / 403 locked are shown by one global sheet (components/GateSheet.jsx).
// Pass `{ _silentGate: true }` in a request config when the screen shows the gate itself.
export const GATE_EVENT = "cz-gate";
export const UNAUTH_EVENT = "cz-unauth";

function emit(name, detail) {
  try { window.dispatchEvent(new CustomEvent(name, { detail })); } catch { /* old browser */ }
}

api.interceptors.response.use(undefined, async (error) => {
  const cfg = error?.config;
  const status = error?.response?.status;
  const url = String(cfg?.url || "");
  if (status === 401 && cfg && !cfg._retried && !NO_RENEW.some((p) => url.includes(p))) {
    try {
      await renewSession();
      cfg._retried = true;
      return api(cfg);
    } catch {
      if (!url.includes("/auth/me")) emit(UNAUTH_EVENT, { url });
      throw error;
    }
  }
  const d = error?.response?.data?.detail;
  // The team disabled this account: treat it like a lost session (back to login, which explains it).
  if (status === 403 && d?.code === "revoked" && !url.includes("/auth/otp/")) emit(UNAUTH_EVENT, { url, revoked: true });
  if ((status === 402 || status === 403) && d && (d.code === "limit" || d.code === "locked") && !cfg?._silentGate) {
    emit(GATE_EVENT, { status, ...d });
  }
  throw error;
});

// 422 validation item → plain sentence ("Target must be at least ₹10,000.") instead of the server's raw wording.
const FIELD = { target_inr: "Target amount", lump_sum_inr: "One-time amount", monthly_inr: "Monthly amount", amount_inr: "Amount",
  goal_name: "Goal name", years: "Years", api_key: "API key", api_secret: "API secret", query: "Your text", question: "Your question",
  text: "Your text", name: "Name", email: "Email", deadline: "Deadline", date: "Date", title: "Title", net_usd_m: "Net flow" };
function plain422(e) {
  const key = Array.isArray(e?.loc) ? e.loc[e.loc.length - 1] : "";
  const label = FIELD[key] || String(key || "This").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  const money = /_inr$/.test(String(key));
  const n = (v) => (money ? `₹${Number(v).toLocaleString("en-IN")}` : Number(v).toLocaleString("en-IN"));
  const c = e?.ctx || {};
  switch (e?.type) {
    case "greater_than_equal": return `${label} must be at least ${n(c.ge)}.`;
    case "greater_than": return `${label} must be more than ${n(c.gt)}.`;
    case "less_than_equal": return `${label} can be at most ${n(c.le)}.`;
    case "less_than": return `${label} must be less than ${n(c.lt)}.`;
    case "string_too_short": return c.min_length > 1 ? `${label} is too short.` : `${label} is required.`;
    case "string_too_long": return `${label} is too long (up to ${c.max_length} characters).`;
    case "missing": return `${label} is required.`;
    case "float_parsing": case "int_parsing": case "float_type": case "int_type": return `${label} must be a number.`;
    case "value_error": return String(e.msg || "").replace(/^Value error, /, "");
    default: return `${label} isn't valid.`;
  }
}

// Human sentence from any API error: {detail: {msg}} | {detail: "…"} | 422 [{msg}].
export function apiError(err, fallback = "Something went wrong. Please try again.") {
  const d = err?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d.msg === "string") return d.msg;
  if (Array.isArray(d)) return d.map(plain422).filter(Boolean).join(" ") || fallback;
  if (err?.message === "Network Error") return "Could not reach the server. Check your internet and try again.";
  if (err?.code === "ECONNABORTED") return "This is taking too long. Please try again.";
  return fallback;
}

export const errCode = (err) => err?.response?.data?.detail?.code || null;
export const errStatus = (err) => err?.response?.status || null;

// GET helper for react-query: `queryFn: get("/verdicts/today")`.
export const get = (path, params) => async () => (await api.get(path, { params })).data;
