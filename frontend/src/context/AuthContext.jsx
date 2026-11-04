// Auth: cookies set by the API; GET /auth/session → {user, plan: PlanInfo, reason}.
//
// /auth/session always answers 200 (renewing from the refresh cookie when needed), so public pages don't log a
// 401 and the app doesn't do a refresh round trip on load.
// `signedOut` records WHY there is no user, so guards can redirect correctly:
//   "logout"  → the member pressed Log out: go to /login with no ?next= (QA 3 Nov: it used to keep the last page)
//   "expired" → the session ran out mid-use: /login?next=<page>&reason=expired, back to the page after login
//   "revoked" → the team disabled the account: /login?reason=revoked, which explains it
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError, UNAUTH_EVENT } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const qc = useQueryClient();
  const [user, setUser] = useState(null);      // null = checking, false = logged out, object = user
  const [plan, setPlan] = useState(null);      // PlanInfo
  const [checking, setChecking] = useState(true);
  const [signedOut, setSignedOut] = useState(null);   // null | "logout" | "expired" | "revoked"
  const hadUser = useRef(false);

  const refreshMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/session");
      setUser(data?.user || false);
      setPlan(data?.plan || null);
      if (data?.user) { hadUser.current = true; setSignedOut(null); }
      else if (data?.reason === "revoked") setSignedOut("revoked");
      else if (hadUser.current) setSignedOut((r) => r || "expired");
      return data;
    } catch {
      setUser(false);
      setPlan(null);
      return null;
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => { refreshMe(); }, [refreshMe]);

  // A request came back 401 even after a refresh: the session is gone.
  useEffect(() => {
    const onUnauth = (e) => {
      setSignedOut((r) => (r === "logout" ? r : e?.detail?.revoked ? "revoked" : "expired"));
      setUser(false); setPlan(null);
    };
    window.addEventListener(UNAUTH_EVENT, onUnauth);
    return () => window.removeEventListener(UNAUTH_EVENT, onUnauth);
  }, []);

  const requestOtp = useCallback(async (phone, channel = "auto") => {
    try {
      const { data } = await api.post("/auth/otp/request", { phone, channel });
      return { ok: true, ...data };
    } catch (e) {
      const d = e?.response?.data?.detail;
      return { ok: false, error: apiError(e), code: d?.code, retryIn: d?.retry_in };
    }
  }, []);

  const verifyOtp = useCallback(async ({ challengeId, phone, code, name, utm, deviceId }) => {
    try {
      const body = { challenge_id: challengeId, phone, code, utm: utm || {}, device_id: deviceId || null };
      if (name && name.trim()) body.name = name.trim();
      const { data } = await api.post("/auth/otp/verify", body);
      await refreshMe();
      return { ok: true, user: data?.user, isNew: data?.is_new };
    } catch (e) {
      const d = e?.response?.data?.detail;
      return { ok: false, error: apiError(e), code: d?.code, attemptsLeft: d?.attempts_left };
    }
  }, [refreshMe]);

  const staffLogin = useCallback(async (email, password) => {
    try {
      await api.post("/auth/staff/login", { email, password });
      const me = await refreshMe();
      return { ok: true, user: me?.user };
    } catch (e) {
      return { ok: false, error: apiError(e, "Email or password is wrong.") };
    }
  }, [refreshMe]);

  const logout = useCallback(async () => {
    setSignedOut("logout");
    try { await api.post("/auth/logout"); } catch { /* noop */ }
    hadUser.current = false;
    setUser(false);
    setPlan(null);
    qc.clear();
  }, [qc]);

  return (
    <AuthCtx.Provider value={{ user, plan, checking, signedOut, refreshMe, setPlan, setUser, requestOtp, verifyOtp, staffLogin, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

// Where a guard sends someone who has no session (see `signedOut` above). `loginPath` = "/login" or "/admin/login".
export function loginRedirect(loginPath, signedOut, here) {
  if (signedOut === "logout") return loginPath;
  if (signedOut === "revoked") return `${loginPath}?reason=revoked`;
  const next = `next=${encodeURIComponent(here)}`;
  return signedOut === "expired" ? `${loginPath}?${next}&reason=expired` : `${loginPath}?${next}`;
}

// Feature access from PlanInfo.features (true/false). Admins see everything.
export function useFeature(key) {
  const { user, plan } = useAuth();
  if (!user) return false;
  if (user.role === "admin") return true;
  return !!plan?.features?.[key];
}
