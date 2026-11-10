// /admin/login — staff email + password (POST /auth/staff/login), or the normal phone OTP.
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import AuthShell, { ReasonNotice } from "../components/AuthShell";
import OtpLogin from "../components/OtpLogin";
import { Button, Field, Input, Segmented } from "../components/ui";

export default function AdminLogin() {
  const { user, staffLogin } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const raw = new URLSearchParams(loc.search).get("next");
  const next = raw && raw.startsWith("/admin") ? raw : "/admin";
  const [mode, setMode] = useState("staff");
  const [f, setF] = useState({ email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (user && user.role === "admin") nav(next, { replace: true }); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    const r = await staffLogin(f.email.trim(), f.password);
    setBusy(false);
    if (!r.ok) { setErr(r.error); return; }
    nav(next, { replace: true });
  };

  return (
    <AuthShell eyebrow="Admin" title="Staff log in." subtitle="Use your staff email and password, or your admin mobile number." notice={<ReasonNotice search={loc.search} />}>
      <Segmented className="mb-6" options={[{ value: "staff", label: "Email" }, { value: "otp", label: "Mobile" }]} value={mode} onChange={setMode} label="Login method" testid="admin-login-mode" />
      {mode === "staff" ? (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email"><Input type="email" autoComplete="username" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoFocus data-testid="staff-email" /></Field>
          <Field label="Password"><Input type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} data-testid="staff-password" /></Field>
          {err && <p className="rounded-bzbtn border border-bz-miss bg-bz-miss-tint px-3.5 py-3 text-[14px] text-bz-miss" role="alert">{err}</p>}
          <Button type="submit" className="w-full h-14" loading={busy} disabled={!f.email || !f.password} data-testid="staff-submit">Log in</Button>
        </form>
      ) : (
        <OtpLogin onDone={() => nav(next, { replace: true })} />
      )}
    </AuthShell>
  );
}
