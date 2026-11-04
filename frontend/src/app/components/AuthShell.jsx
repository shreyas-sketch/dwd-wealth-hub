// Two-pane sign-in (Bullzeye AuthShell) in the Coinzeye tokens: brand rail on a computer, form on the right.
import { Link } from "react-router-dom";
import { ThemeToggle } from "@/context/ThemeContext";
import brand from "@/brand";
import Logo, { LogoMark } from "./Logo";

export default function AuthShell({ eyebrow, title, subtitle, children, footer }) {
  return (
    <div className="min-h-screen w-full flex items-stretch bg-bz-bg text-bz-ink font-bz" data-testid="auth-shell">
      <aside className="hidden lg:flex lg:w-[44%] relative overflow-hidden border-r border-bz-line bg-bz-panel">
        <div className="absolute inset-0 pointer-events-none" style={{ background: "radial-gradient(circle at 25% 20%, var(--bz-gold-tint) 0%, transparent 55%), radial-gradient(circle at 80% 85%, var(--bz-accent-tint) 0%, transparent 60%)" }} />
        <div className="relative z-10 flex flex-col justify-between p-14 w-full">
          <Link to="/"><Logo big /></Link>
          <div className="space-y-5 max-w-md">
            <p className="font-bzmono text-[11px] tracking-[0.28em] uppercase text-bz-gold-deep">X-Ray · Verdicts · Plan</p>
            <h2 className="font-bzserif text-[44px] leading-[1.05] font-semibold">{brand.tagline}.</h2>
            <p className="text-[16px] leading-relaxed text-bz-muted">Check coins and tips for scams, see the daily call on the top coins, and grow a simple plan in rupees.</p>
          </div>
          <p className="font-bzmono text-[10.5px] tracking-[0.2em] uppercase text-bz-muted">Education and research, not investment advice.</p>
        </div>
      </aside>
      <main className="flex-1 flex flex-col">
        <div className="flex items-center justify-between px-5 sm:px-10 pt-5">
          <Link to="/" className="lg:hidden flex items-center gap-2"><LogoMark size={30} /><span className="font-bzserif text-[18px] font-semibold">{brand.name}</span></Link>
          <span className="hidden lg:block" />
          <ThemeToggle />
        </div>
        <div className="flex-1 flex items-center justify-center p-5 sm:p-10">
          <div className="w-full max-w-[420px]">
            {eyebrow && <p className="font-bzmono text-[11px] tracking-[0.28em] uppercase text-bz-gold-deep mb-3">{eyebrow}</p>}
            <h1 className="font-bzserif text-[32px] leading-tight font-semibold">{title}</h1>
            {subtitle && <p className="mt-2.5 text-[15px] text-bz-muted leading-relaxed">{subtitle}</p>}
            <div className="mt-8">{children}</div>
            {footer && <div className="mt-8 pt-5 border-t border-bz-line text-[12px] text-bz-muted leading-relaxed">{footer}</div>}
          </div>
        </div>
      </main>
    </div>
  );
}
