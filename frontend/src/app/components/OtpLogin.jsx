// Mobile OTP: phone → POST /auth/otp/request → 6-digit code (+ name if new) → POST /auth/otp/verify.
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { deviceId, getUtm } from "@/lib/attribution";
import { Button, inputCls } from "./ui";

const digits = (s) => String(s || "").replace(/\D/g, "");

export default function OtpLogin({ onDone, onStep }) {
  const { requestOtp, verifyOtp } = useAuth();
  const [step, setStep] = useState("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [ch, setCh] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(0);
  const codeRef = useRef(null);

  useEffect(() => { onStep?.(step, ch); }, [step, ch]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (wait <= 0) return undefined;
    const t = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);

  const send = async (channel = "auto") => {
    setErr("");
    const ph = digits(phone).slice(-10);
    if (ph.length !== 10) { setErr("Enter your 10-digit mobile number."); return; }
    setBusy(true);
    const r = await requestOtp(ph, channel);
    setBusy(false);
    if (!r.ok) { setErr(r.error); if (r.retryIn) setWait(r.retryIn); return; }
    setCh(r); setStep("code"); setCode(""); setWait(r.resend_in || 30);
    setTimeout(() => codeRef.current?.focus(), 50);
  };

  const verify = async (value = code) => {
    if (value.length !== 6 || busy) return;
    setErr(""); setBusy(true);
    const r = await verifyOtp({ challengeId: ch?.challenge_id, phone: digits(phone).slice(-10), code: value,
      name: ch?.is_new ? name : undefined, utm: getUtm(), deviceId: deviceId() });
    setBusy(false);
    if (!r.ok) {
      setErr(r.attemptsLeft != null ? `${r.error} ${r.attemptsLeft} tries left.` : r.error);
      if (["too_many_attempts", "expired", "invalid_challenge"].includes(r.code)) setStep("phone");
      return;
    }
    onDone?.(r);
  };

  if (step === "phone") {
    return (
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="space-y-4">
        <label className="block">
          <span className="block text-[14px] font-semibold text-bz-muted mb-1.5">Mobile number</span>
          <div className="relative">
            <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[19px] font-semibold text-bz-muted">+91</span>
            <input id="phone" type="tel" inputMode="numeric" autoComplete="tel-national" placeholder="98765 43210" autoFocus
              value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={14} data-testid="login-phone"
              className={`${inputCls} h-14 pl-14 text-[20px] font-semibold tracking-wide tabular`} />
          </div>
        </label>
        {err && <p className="rounded-bzbtn border border-bz-miss bg-bz-miss-tint px-3.5 py-3 text-[14px] text-bz-miss" role="alert" data-testid="login-error">{err}</p>}
        <Button type="submit" className="w-full h-14" loading={busy} disabled={busy || wait > 0} data-testid="login-send">
          {busy ? "Sending" : wait > 0 ? `Try again in ${wait}s` : "Send code"}
        </Button>
        <p className="text-[13px] text-bz-muted">New here? The same step creates your free account.</p>
      </form>
    );
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); verify(); }} className="space-y-4">
      <label className="block">
        <span className="flex items-baseline justify-between mb-2">
          <span className="text-[14px] font-semibold text-bz-muted">6-digit code</span>
          <button type="button" onClick={() => { setStep("phone"); setErr(""); }} className="text-[14px] font-semibold text-bz-muted underline underline-offset-4 hover:text-bz-ink py-1" data-testid="login-change">Change number</button>
        </span>
        <input id="code" ref={codeRef} type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="······"
          value={code} data-testid="login-code"
          onChange={(e) => { const v = digits(e.target.value).slice(0, 6); setCode(v); if (v.length === 6 && !ch?.is_new) verify(v); }}
          className={`${inputCls} h-16 text-center font-bzdisplay text-[31px] font-bold tracking-[0.45em] tabular`} />
      </label>
      {ch?.is_new && (
        <label className="block">
          <span className="block text-[14px] font-semibold text-bz-muted mb-1.5">Your name (optional)</span>
          <input type="text" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ramesh" maxLength={60}
            data-testid="login-name" className={inputCls} />
        </label>
      )}
      {ch?.dev_code && (
        <p className="rounded-bzbtn bg-bz-gold-tint text-bz-gold-deep px-3 py-2 text-[14px] font-semibold" data-testid="login-dev-code">
          QA mode · code <button type="button" className="underline font-semibold" onClick={() => { setCode(String(ch.dev_code)); if (!ch.is_new) verify(String(ch.dev_code)); }}>{ch.dev_code}</button>
        </p>
      )}
      {err && <p className="rounded-bzbtn border border-bz-miss bg-bz-miss-tint px-3.5 py-3 text-[14px] text-bz-miss" role="alert" data-testid="login-error">{err}</p>}
      <Button type="submit" className="w-full h-14" loading={busy} disabled={busy || code.length !== 6} data-testid="login-verify">
        {busy ? "Checking" : ch?.is_new ? "Create my account" : "Log in"}
      </Button>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[14px]">
        {wait > 0 ? <span className="text-bz-muted">Resend in {wait}s</span>
          : <button type="button" className="text-bz-accent font-semibold py-1" onClick={() => send("auto")} data-testid="login-resend">Resend code</button>}
        {ch?.channel === "whatsapp" && wait <= 0 && <button type="button" className="text-bz-accent font-semibold py-1" onClick={() => send("sms")}>Send by SMS instead</button>}
      </div>
    </form>
  );
}
