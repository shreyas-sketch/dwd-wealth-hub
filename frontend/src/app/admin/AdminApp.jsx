// Admin panel (/admin/*), role admin only. The staff side is marked by an indigo rail (the member app has a light
// one), so nobody mistakes which side they are on; the content area stays quiet and dense.
import { useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { loginRedirect, useAuth } from "@/context/AuthContext";
import { ThemeToggle } from "@/context/ThemeContext";
import Logo from "../components/Logo";
import { Button, Card, Spinner } from "../components/ui";
import Pulse from "./Pulse";
import Webinar from "./Webinar";
import Users from "./Users";
import AdminAirdrops from "./Airdrops";
import AdminBaskets from "./Baskets";
import AdminEvents from "./Events";
import AdminPicks from "./Picks";
import AdminCrashNotes from "./CrashNotes";
import AdminKnowledge from "./Knowledge";
import AdminEtfFlows from "./EtfFlows";
import AdminFeatures from "./Features";
import AdminSettings from "./Settings";
import AdminVendors from "./Vendors";
import AdminJobs from "./Jobs";

export const GROUPS = [
  { name: "Overview", pages: [{ path: "", label: "Pulse", el: Pulse }, { path: "webinar", label: "Webinar", el: Webinar }] },
  { name: "People", pages: [{ path: "users", label: "Users", el: Users }] },
  { name: "Content", pages: [
    { path: "airdrops", label: "Airdrops", el: AdminAirdrops },
    { path: "baskets", label: "Baskets", el: AdminBaskets },
    { path: "events", label: "Events calendar", el: AdminEvents },
    { path: "picks", label: "Monday Picks", el: AdminPicks },
    { path: "crash-notes", label: "Crash notes", el: AdminCrashNotes },
    { path: "kb", label: "Knowledge base", el: AdminKnowledge },
    { path: "etf-flows", label: "ETF flows", el: AdminEtfFlows },
  ] },
  { name: "Control", pages: [
    { path: "features", label: "Features", el: AdminFeatures },
    { path: "settings", label: "Settings", el: AdminSettings },
    { path: "vendors", label: "Vendors", el: AdminVendors },
    { path: "jobs", label: "Jobs", el: AdminJobs },
  ] },
];
const ALL = GROUPS.flatMap((g) => g.pages);

function SideNav({ onGo }) {
  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="px-2 flex flex-col gap-1">
        <Link to="/admin" onClick={onGo}><Logo onHero /></Link>
        <span className="text-[14px] font-semibold text-bz-gold">Staff panel</span>
      </div>
      <nav aria-label="Admin" className="flex flex-col gap-3 overflow-y-auto">
        {GROUPS.map((g) => (
          <div key={g.name}>
            <div className="px-3 pb-1 text-[13px] font-semibold text-bz-hero-muted">{g.name}</div>
            {g.pages.map((p) => (
              <NavLink key={p.path} to={`/admin${p.path ? `/${p.path}` : ""}`} end onClick={onGo} data-testid={`admin-nav-${p.path || "pulse"}`}
                className={({ isActive }) => `relative block h-10 leading-10 px-3 rounded-bzbtn text-[15px] ${isActive ? "bg-white/10 text-bz-hero-ink font-semibold" : "text-bz-hero-muted hover:bg-white/5 hover:text-bz-hero-ink"}`}>
                {({ isActive }) => (<>{isActive && <span aria-hidden className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-bz-gold" />}{p.label}</>)}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="mt-auto px-2 pt-3 border-t border-bz-hero-line flex items-center justify-between gap-2">
        <Link to="/app" className="text-[14px] font-semibold text-bz-hero-ink underline decoration-bz-gold decoration-2 underline-offset-4">Member app</Link>
        <ThemeToggle />
      </div>
    </div>
  );
}

function Shell() {
  const { pathname } = useLocation();
  const [drawer, setDrawer] = useState(false);
  const sub = pathname.replace(/^\/admin\/?/, "").split("/")[0];
  const page = ALL.find((p) => p.path === sub) || ALL[0];
  return (
    <div className="min-h-screen bg-bz-bg font-bz text-bz-ink antialiased lg:flex">
      <aside className="hidden lg:flex flex-col w-[248px] shrink-0 bg-bz-hero text-bz-hero-ink px-4 py-6 h-screen sticky top-0">
        <SideNav />
      </aside>
      <header className="lg:hidden sticky top-0 z-30 bg-bz-bg border-b border-bz-line h-14 px-4 flex items-center justify-between">
        <button aria-label="Menu" onClick={() => setDrawer(true)} className="w-11 h-11 grid place-items-center rounded-full bg-bz-inset" data-testid="admin-menu">
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <div className="font-bzdisplay text-[20px] font-bold">{page.label}</div>
        <Link to="/admin/users" aria-label="Find a user" className="w-11 h-11 grid place-items-center rounded-full bg-bz-inset">
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        </Link>
      </header>
      {drawer && (
        <div className="lg:hidden fixed inset-0 z-40">
          <button aria-label="Close menu" className="absolute inset-0 bg-bz-scrim" onClick={() => setDrawer(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-[280px] bg-bz-hero text-bz-hero-ink px-4 py-5 overflow-y-auto shadow-bzsheet flex flex-col">
            <SideNav onGo={() => setDrawer(false)} />
          </div>
        </div>
      )}
      <main className="flex-1 min-w-0 px-4 lg:px-9 py-5 lg:py-7 max-w-[1240px]">
        <h1 className="hidden lg:block font-bzdisplay text-[39px] font-bold leading-[1.05] mb-6">{page.label}</h1>
        <Routes>
          {ALL.map((p) => {
            const El = p.el;
            return p.path ? <Route key={p.path} path={p.path} element={<El />} /> : <Route key="index" index element={<El />} />;
          })}
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function AdminApp() {
  const { user, checking, signedOut, logout } = useAuth();
  const nav = useNavigate();
  const { pathname } = useLocation();
  if (checking || user === null) return <div className="min-h-screen bg-bz-bg grid place-items-center"><Spinner /></div>;
  if (!user) return <Navigate to={loginRedirect("/admin/login", signedOut, pathname)} replace />;
  if (user.role !== "admin") {
    return (
      <div className="min-h-screen bg-bz-bg font-bz text-bz-ink grid place-items-center p-5">
        <Card className="max-w-[440px] w-full text-center" data-testid="admin-denied">
          <p className="font-bzdisplay text-[25px] font-bold">Staff only</p>
          <p className="text-[15px] text-bz-muted mt-2">This account ({user.phone || user.email}) doesn't have admin access. Ask the team to add your number, or log in with a staff account.</p>
          <div className="flex flex-col gap-2 mt-5">
            <Button onClick={async () => { await logout(); nav("/admin/login", { replace: true }); }}>Log in as staff</Button>
            <Link to="/app" className="text-sm font-semibold text-bz-accent py-2">Back to the app</Link>
          </div>
        </Card>
      </div>
    );
  }
  return <Shell />;
}
