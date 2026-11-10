// Two-pane sign-in (Bullzeye AuthShell) in the Coinzeye tokens: brand rail on a computer, form on the right.
import { Link } from "react-router-dom";
import { ThemeToggle } from "@/context/ThemeContext";
import brand from "@/brand";
import Logo, { LogoMark } from "./Logo";

// Why someone landed on a login page (?reason=, set by the auth guards in context/AuthContext.jsx).
const REASONS = {
  expired: { tone: "muted", text: "Your session ended. Log in again to carry on where you were." },
  revoked: { tone: "miss", text: "This account has been disabled. If you think this is a mistake, contact the DWD support team." },
};

export function ReasonNotice({ search }) {
  const r = REASONS[new URLSearchParams(search || "").get("reason")];
  if (!r) return null;
  return (
    <p role="status" data-testid="login-reason"
      className={`mb-5 rounded-bzbtn border px-3.5 py-2.5 text-[14px] ${r.tone === "miss" ? "border-bz-miss text-bz-miss bg-bz-miss-tint" : "border-bz-line bg-bz-inset text-bz-ink"}`}>
      {r.text}
    </p>
  );
}

export default function AuthShell({ eyebrow, title, subtitle, children, footer, notice = null }) {
  return (
    <div className="min-h-screen w-full flex items-stretch bg-bz-bg text-bz-ink font-bz" data-testid="auth-shell">
      <aside className="hidden lg:flex lg:w-[44%] relative overflow-hidden bg-bz-hero text-bz-hero-ink">
        <div className="relative z-10 flex flex-col justify-between p-14 w-full">
          <Link to="/"><Logo big onHero /></Link>
          <div className="space-y-5 max-w-md">
            <h2 className="font-bzdisplay text-[49px] leading-[1.02] font-bold text-bz-hero-ink">{brand.tagline.replace(/-/g, "\u2011")}.</h2>
            <p className="text-[17px] leading-relaxed text-bz-hero-muted">Check coins and tips for scams, see the daily call on the top coins, and grow a simple plan in rupees.</p>
          </div>
          <p className="text-[14px] text-bz-hero-muted">Education and research, not investment advice.</p>
        </div>
      </aside>
      <main className="flex-1 flex flex-col">
        <div className="flex items-center justify-between px-5 sm:px-10 pt-5">
          <Link to="/" className="lg:hidden flex items-center gap-2"><LogoMark size={30} /><span className="font-bzdisplay text-[20px] font-bold">{brand.name}</span></Link>
          <span className="hidden lg:block" />
          <ThemeToggle />
        </div>
        <div className="flex-1 flex items-center justify-center p-5 sm:p-10">
          <div className="w-full max-w-[420px]">
            {notice}
            {eyebrow && <p className="text-[15px] font-semibold text-bz-gold-deep mb-1">{eyebrow}</p>}
            <h1 className="font-bzdisplay text-[31px] sm:text-[39px] leading-[1.08] font-bold">{title}</h1>
            {subtitle && <p className="mt-2.5 text-[15px] text-bz-muted leading-relaxed">{subtitle}</p>}
            <div className="mt-8">{children}</div>
            {footer && <div className="mt-8 pt-5 border-t border-bz-line text-[12px] text-bz-muted leading-relaxed">{footer}</div>}
          </div>
        </div>
      </main>
    </div>
  );
}
