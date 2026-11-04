// Auth: cookies set by the API; /auth/me → {user, plan: PlanInfo}.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError, UNAUTH_EVENT } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const qc = useQueryClient();
  const [user, setUser] = useState(null);      // null = checking, false = logged out, object = user
  const [plan, setPlan] = useState(null);      // PlanInfo
  const [checking, setChecking] = useState(true);

  const refreshMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data?.user || false);
      setPlan(data?.plan || null);
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
    const onUnauth = () => { setUser(false); setPlan(null); };
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
    try { await api.post("/auth/logout"); } catch { /* noop */ }
    setUser(false);
    setPlan(null);
    qc.clear();
  }, [qc]);

  return (
    <AuthCtx.Provider value={{ user, plan, checking, refreshMe, setPlan, setUser, requestOtp, verifyOtp, staffLogin, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

// Feature access from PlanInfo.features (true/false). Admins see everything.
export function useFeature(key) {
  const { user, plan } = useAuth();
  if (!user) return false;
  if (user.role === "admin") return true;
  return !!plan?.features?.[key];
}
