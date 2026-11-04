// Member app shell (from Bullzeye AppShell): left sidebar with one-line descriptions on a computer;
// on a phone a top bar with ☰ (drawer) and a bottom bar: Today · X-Ray · Verdicts · My Plan · Menu.
import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight, Bell, CalendarDays, CandlestickChart, CreditCard, Gift, Home, Layers, Lock, LogOut, Menu,
  MessageCircle, Newspaper, Radar, Repeat, ScanSearch, Scale, Shield, Target, User, X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ThemeToggle } from "@/context/ThemeContext";
import { captureAttribution, track } from "@/lib/attribution";
import { daysUntil } from "@/lib/format";
import brand from "@/brand";
import Logo from "./Logo";
import { PlanChip } from "./common";
import { Spinner } from "./ui";

export const NAV_MAIN = [
  { to: "/app", key: "today", label: "Today", sub: "Your day at a glance", icon: Home, end: true },
  { to: "/app/xray", key: "xray", label: "Coin X-Ray", sub: "Is this coin or tip a scam?", icon: ScanSearch, feature: "xray" },
  { to: "/app/verdicts", key: "verdicts", label: "Verdicts", sub: "Daily call on the top coins", icon: Scale, feature: "verdicts" },
  { to: "/app/plan", key: "plan", label: "My Plan", sub: "Goal plan + paper money", icon: Target, feature: "plan" },
  { to: "/app/airdrops", key: "airdrops", label: "Airdrops", sub: "Free tokens, checked for scams", icon: Gift, feature: "airdrops" },
  { to: "/app/autopilot", key: "autopilot", label: "SIP Autopilot", sub: "Auto-buy every week or month", icon: Repeat, feature: "autopilot" },
  { to: "/app/chart", key: "chart", label: "Chart Reader", sub: "Upload a chart, get a read", icon: CandlestickChart, feature: "chart" },
];
export const NAV_PRO = [
  { to: "/app/ask", key: "ask", label: `Ask ${brand.coach} AI`, sub: "Your crypto teacher, any time", icon: MessageCircle, feature: "ask" },
  { to: "/app/baskets", key: "baskets", label: "Baskets", sub: "Ready-made coin groups", icon: Layers, feature: "baskets" },
  { to: "/app/radar", key: "radar", label: "Early Coin Radar", sub: "New and trending coins", icon: Radar, feature: "radar" },
  { to: "/app/calendar", key: "calendar", label: "Events Calendar", sub: "Dates that move prices", icon: CalendarDays, feature: "calendar" },
  { to: "/app/p2p", key: "p2p", label: "P2P Rates", sub: "Best ₹ → USDT rates", icon: ArrowLeftRight, feature: "p2p" },
  { to: "/app/news", key: "news", label: "News Decoder", sub: "News in plain words", icon: Newspaper, feature: "news" },
];
const NAV_ACCOUNT = [
  { to: "/app/inbox", key: "inbox", label: "Inbox", sub: "Your alerts", icon: Bell },
  { to: "/app/plans", key: "plans", label: "Plans", sub: "Free, ₹2,000 and ₹5,000", icon: CreditCard },
  { to: "/app/account", key: "account", label: "Account", sub: "Profile, usage, theme", icon: User },
];
const BAR = [NAV_MAIN[0], NAV_MAIN[1], NAV_MAIN[2], NAV_MAIN[3]];

const iconBtn = "w-11 h-11 grid place-items-center rounded-full border border-bz-line text-bz-muted hover:text-bz-ink hover:bg-bz-inset";

function NavItem({ item, onGo, locked, badge }) {
  const { to, key, label, sub, icon: Icon, end } = item;
  return (
    <NavLink to={to} end={end} onClick={onGo} data-testid={`nav-${key}`}
      className={({ isActive }) => `relative flex items-center gap-3 px-3 py-2.5 rounded-[10px] min-h-[48px] ${isActive ? "bg-bz-inset" : "hover:bg-bz-inset"}`}>
      {({ isActive }) => (
        <>
          {isActive && <span aria-hidden className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-bz-gold" />}
          <Icon className={`w-5 h-5 shrink-0 ${isActive ? "text-bz-gold" : "text-bz-muted"}`} strokeWidth={1.75} aria-hidden />
          <span className="min-w-0 flex-1">
            <span className={`flex items-center gap-1.5 text-[14px] font-medium`}>
              <span className={isActive ? "text-bz-ink" : "text-bz-muted"}>{label}</span>
              {locked && <Lock className="w-3 h-3 text-bz-muted" aria-label="Locked on your plan" />}
            </span>
            <span className="block text-[12px] text-bz-muted truncate">{sub}</span>
          </span>
          {badge ? <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-bz-gold text-white text-[11px] font-semibold grid place-items-center">{badge}</span> : null}
        </>
      )}
    </NavLink>
  );
}

function GroupLabel({ children }) {
  return <div className="px-3 pt-4 pb-1 font-bzmono text-[10.5px] uppercase tracking-[0.22em] text-bz-gold-deep">{children}</div>;
}

function MenuBody({ onGo, user, plan, unread, onLogout }) {
  const feat = plan?.features || {};
  const admin = user?.role === "admin";
  const locked = (i) => i.feature && !admin && !feat[i.feature];
  const initial = (user?.name || user?.phone || "?").replace(/^\+91/, "").slice(0, 1).toUpperCase();
  const trialDays = plan?.source === "trial" ? daysUntil(plan?.trial_ends_at) : null;
  return (
    <div className="flex flex-col h-full min-h-0">
      <Link to="/app" onClick={onGo} className={`px-2 ${onGo ? "mr-12" : ""}`} aria-label={`${brand.name} home`}><Logo /></Link>
      <div className="mt-4 px-2 flex flex-wrap items-center gap-2">
        <PlanChip plan={plan} />
        {trialDays != null && <span className="text-[12px] font-semibold text-bz-gold-deep" data-testid="trial-left">Trial ends in {trialDays} day{trialDays === 1 ? "" : "s"}</span>}
      </div>
      <nav aria-label="Main" className="mt-3 flex flex-col gap-0.5 overflow-y-auto no-scrollbar -mx-1 px-1 pb-2 flex-1 min-h-0">
        {NAV_MAIN.map((i) => <NavItem key={i.to} item={i} onGo={onGo} locked={locked(i)} />)}
        <GroupLabel>₹5,000 plan</GroupLabel>
        {NAV_PRO.map((i) => <NavItem key={i.to} item={i} onGo={onGo} locked={locked(i)} />)}
        <GroupLabel>You</GroupLabel>
        {NAV_ACCOUNT.map((i) => <NavItem key={i.to} item={i} onGo={onGo} badge={i.key === "inbox" ? unread : 0} />)}
        {admin && <NavItem item={{ to: "/admin", key: "admin", label: "Admin panel", sub: "Staff only", icon: Shield }} onGo={onGo} />}
      </nav>
      <div className="pt-3 border-t border-bz-line flex items-center gap-3 px-2">
        <Link to="/app/account" onClick={onGo} className="flex items-center gap-3 min-w-0 flex-1 rounded-[10px] hover:bg-bz-inset -m-1 p-1">
          <span className="w-9 h-9 shrink-0 rounded-full grid place-items-center text-[13px] font-semibold bg-bz-gold text-white">{initial}</span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold truncate">{user?.name || user?.phone}</span>
            <span className="block font-bzmono text-[10.5px] uppercase tracking-[0.16em] text-bz-muted">Profile</span>
          </span>
        </Link>
        <button type="button" onClick={onLogout} title="Log out" aria-label="Log out" data-testid="logout" className="w-10 h-10 grid place-items-center text-bz-muted hover:text-bz-ink shrink-0">
          <LogOut className="w-4 h-4" strokeWidth={1.6} />
        </button>
      </div>
    </div>
  );
}

// Redirects to /login?next=… when logged out.
export function RequireAuth({ children }) {
  const { user, checking } = useAuth();
  const { pathname, search } = useLocation();
  if (checking || user === null) return <div className="min-h-screen bg-bz-bg grid place-items-center"><Spinner /></div>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  return children;
}

export default function AppShell() {
  const { user, plan, logout } = useAuth();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const [drawer, setDrawer] = useState(false);

  useEffect(() => { captureAttribution(search); }, [search]);
  useEffect(() => { track("page_view", { path: pathname }); setDrawer(false); window.scrollTo(0, 0); }, [pathname]);

  const inbox = useQuery({ queryKey: ["inbox"], queryFn: async () => (await api.get("/inbox")).data, enabled: !!user, staleTime: 60_000 });
  const unread = inbox.data?.unread || 0;
  const menu = { user, plan, unread, onLogout: async () => { await logout(); navigate("/login", { replace: true }); } };

  return (
    <div className="min-h-screen flex bg-bz-bg font-bz text-bz-ink antialiased">
      <aside className="hidden lg:flex flex-col w-[272px] shrink-0 px-4 py-6 sticky top-0 h-screen border-r border-bz-line bg-bz-panel">
        <MenuBody {...menu} />
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="sticky top-0 z-30 lg:static bg-bz-bg border-b border-bz-line lg:border-0">
          <div className="flex items-center justify-between gap-3 px-4 md:px-10 h-16 lg:h-auto lg:pt-4 lg:pb-2">
            <div className="flex items-center gap-2 lg:hidden min-w-0">
              <button type="button" aria-label="Open menu" data-testid="menu-open" onClick={() => setDrawer(true)} className={iconBtn}>
                <Menu className="w-5 h-5" strokeWidth={1.75} aria-hidden />
              </button>
              <Link to="/app" aria-label={`${brand.name} home`}><Logo word="hidden min-[380px]:inline" /></Link>
            </div>
            <span className="hidden lg:block" />
            <div className="flex items-center gap-2">
              <Link to="/app/inbox" aria-label={`Inbox${unread ? `, ${unread} unread` : ""}`} className={`${iconBtn} relative`} data-testid="topbar-inbox">
                <Bell className="w-5 h-5" strokeWidth={1.75} aria-hidden />
                {unread > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-bz-gold text-white text-[10px] font-semibold grid place-items-center">{unread > 9 ? "9+" : unread}</span>}
              </Link>
              <ThemeToggle />
            </div>
          </div>
        </header>

        {drawer && (
          <div className="lg:hidden fixed inset-0 z-50">
            <button type="button" aria-label="Close menu" className="absolute inset-0 bg-bz-scrim" onClick={() => setDrawer(false)} />
            <div className="absolute left-0 top-0 bottom-0 w-[320px] max-w-[88vw] bg-bz-panel border-r border-bz-line px-4 pt-5 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-xl flex flex-col">
              <button type="button" aria-label="Close menu" onClick={() => setDrawer(false)} className={`${iconBtn} absolute right-3 top-4`}>
                <X className="w-5 h-5" strokeWidth={1.75} aria-hidden />
              </button>
              <MenuBody {...menu} onGo={() => setDrawer(false)} />
            </div>
          </div>
        )}

        <main className="flex-1 px-4 md:px-10 lg:px-14 pt-5 md:pt-8 pb-28 lg:pb-16">
          <div className="max-w-[980px] mx-auto">
            <Outlet />
          </div>
        </main>

        <nav aria-label="Quick" className="lg:hidden fixed bottom-0 inset-x-0 z-30 bg-bz-panel border-t border-bz-line pb-[env(safe-area-inset-bottom)]">
          <ul className="max-w-[600px] mx-auto grid grid-cols-5">
            {BAR.map(({ to, key, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} data-testid={`bar-${key}`}
                  className={({ isActive }) => `flex flex-col items-center gap-1 pt-2.5 pb-3 text-[11.5px] font-medium ${isActive ? "text-bz-ink" : "text-bz-muted hover:text-bz-ink"}`}>
                  {({ isActive }) => (<><Icon className={`w-5 h-5 ${isActive ? "text-bz-gold" : ""}`} strokeWidth={1.75} aria-hidden />{key === "xray" ? "X-Ray" : key === "plan" ? "My Plan" : label}</>)}
                </NavLink>
              </li>
            ))}
            <li>
              <button type="button" onClick={() => setDrawer(true)} data-testid="bar-menu"
                className="w-full flex flex-col items-center gap-1 pt-2.5 pb-3 text-[11.5px] font-medium text-bz-muted hover:text-bz-ink relative">
                <Menu className="w-5 h-5" strokeWidth={1.75} aria-hidden />Menu
                {unread > 0 && <span className="absolute top-1.5 right-[calc(50%-18px)] w-2 h-2 rounded-full bg-bz-gold" aria-hidden />}
              </button>
            </li>
          </ul>
        </nav>
      </div>
    </div>
  );
}
