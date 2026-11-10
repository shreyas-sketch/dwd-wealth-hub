// /login — mobile OTP (Bullzeye Login look). After login: ?next= or /app.
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { captureAttribution } from "@/lib/attribution";
import AuthShell, { ReasonNotice } from "../components/AuthShell";
import OtpLogin from "../components/OtpLogin";
import { newAccountLine, useTrialDays } from "@/lib/trial";

function safeNext(n) {
  return n && n.startsWith("/") && !n.startsWith("//") ? n : "/app";
}

export default function Login() {
  const { user } = useAuth();
  const trialDays = useTrialDays();
  const nav = useNavigate();
  const loc = useLocation();
  const next = safeNext(new URLSearchParams(loc.search).get("next"));
  const [step, setStep] = useState({ s: "phone", ch: null });

  useEffect(() => { captureAttribution(loc.search); }, [loc.search]);
  useEffect(() => { if (user) nav(next, { replace: true }); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const legal = (
    <span>By continuing you agree to the <Link to="/terms" className="text-bz-accent">Terms</Link>, <Link to="/privacy" className="text-bz-accent">Privacy policy</Link> and <Link to="/disclosures" className="text-bz-accent">Risk disclosures</Link>. Crypto is unregulated in India and risky.</span>
  );
  const code = step.s === "code";
  return (
    <AuthShell
      eyebrow={code ? "Verify" : "Log in or sign up"}
      title={code ? "Enter the code." : "Log in with your mobile number."}
      subtitle={code ? `Sent by ${step.ch?.channel === "whatsapp" ? "WhatsApp" : "SMS"} to ${step.ch?.sent_to || "your number"}.` : `We'll send a 6-digit code. ${newAccountLine(trialDays)}`}
      footer={legal}
      notice={code ? null : <ReasonNotice search={loc.search} />}
    >
      <OtpLogin onStep={(s, ch) => setStep({ s, ch })} onDone={() => nav(next, { replace: true })} />
    </AuthShell>
  );
}
