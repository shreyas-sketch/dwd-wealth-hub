// Header + footer for public pages (/, /plans, legal).
import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ThemeToggle } from "@/context/ThemeContext";
import { captureAttribution, track } from "@/lib/attribution";
import brand from "@/brand";
import Logo from "./Logo";

export default function PublicLayout({ children, wide = false }) {
  const { user } = useAuth();
  const { pathname, search } = useLocation();
  useEffect(() => { captureAttribution(search); }, [search]);
  useEffect(() => { track("page_view", { path: pathname }); }, [pathname]);
  return (
    <div className="min-h-screen flex flex-col bg-bz-bg font-bz text-bz-ink antialiased">
      <header className="sticky top-0 z-30 bg-bz-bg/95 backdrop-blur border-b border-bz-line">
        <div className={`mx-auto ${wide ? "max-w-[1120px]" : "max-w-[980px]"} px-4 md:px-8 h-16 flex items-center justify-between gap-3`}>
          <Link to="/" aria-label={`${brand.name} home`}><Logo word="hidden min-[360px]:inline" /></Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {user ? (
              <Link to="/app" data-testid="open-app" className="inline-flex items-center h-11 px-5 rounded-full bg-bz-btn text-bz-on-btn text-[15px] font-semibold">Open app</Link>
            ) : (
              <Link to="/login" data-testid="header-login" className="inline-flex items-center h-11 px-5 rounded-full bg-bz-btn text-bz-on-btn text-[15px] font-semibold hover:opacity-90">Log in or sign up</Link>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-bz-line bg-bz-panel">
        <div className={`mx-auto ${wide ? "max-w-[1120px]" : "max-w-[980px]"} px-4 md:px-8 py-8 space-y-3`}>
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-[14px]">
            <Link to="/plans" className="text-bz-muted hover:text-bz-ink">Plans</Link>
            <Link to="/terms" className="text-bz-muted hover:text-bz-ink">Terms</Link>
            <Link to="/privacy" className="text-bz-muted hover:text-bz-ink">Privacy</Link>
            <Link to="/disclosures" className="text-bz-muted hover:text-bz-ink">Risk disclosures</Link>
          </div>
          <p className="text-[12px] leading-relaxed text-bz-muted max-w-[760px]">
            {brand.name} is an education and research tool, not investment advice. Crypto is unregulated in India and highly risky;
            prices can fall sharply and you can lose most of your money. Gains are taxed at 30% and 1% TDS applies on sales.
          </p>
          <p className="text-[12px] text-bz-muted">© {new Date().getFullYear()} {brand.name}</p>
        </div>
      </footer>
    </div>
  );
}
