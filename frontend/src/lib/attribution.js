// Attribution (from Bullzeye bz/lib.js captureAttribution): utm_* and ?src= captured on first landing,
// sent as `utm` on OTP verify. Best effort only — storage may be blocked.
import { api } from "./api";

const KEY = "cz_attr";
const PARAMS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "src", "gclid", "fbclid"];

export function captureAttribution(search = window.location.search) {
  try {
    const q = new URLSearchParams(search);
    const cur = JSON.parse(localStorage.getItem(KEY) || "{}");
    const utm = { ...(cur.utm || {}) };
    let changed = false;
    PARAMS.forEach((k) => {
      if (q.get(k) && !utm[k]) { utm[k] = q.get(k); changed = true; }
    });
    if (changed) {
      if (!utm.landing) utm.landing = window.location.pathname;
      localStorage.setItem(KEY, JSON.stringify({ ...cur, utm }));
    }
  } catch { /* storage blocked */ }
}

export function getUtm() {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}").utm || {}; } catch { return {}; }
}

export function deviceId() {
  try {
    let d = localStorage.getItem("cz_device");
    if (!d) {
      d = (window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random()}`).replace(/[^a-zA-Z0-9-]/g, "").slice(0, 60);
      localStorage.setItem("cz_device", d);
    }
    return d;
  } catch { return null; }
}

// Client analytics: page_view, tool_opened, upgrade_viewed, checkout_opened, share_clicked.
export function track(name, props = {}) {
  api.post("/events", { name, props }).catch(() => {});
}
