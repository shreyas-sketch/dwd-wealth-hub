// Route map — see README.md. Public: / /login /plans /terms /privacy /disclosures.
// Member app (/app/*) inside AppShell, login required. Admin (/admin/*) role admin only.
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import AppShell, { RequireAuth } from "@/app/components/AppShell";
import GateSheet from "@/app/components/GateSheet";
import { ConfirmProvider } from "@/app/components/Confirm";
import { Spinner } from "@/app/components/ui";
import Landing from "@/app/pages/Landing";
import Login from "@/app/pages/Login";
import PublicPlans from "@/app/pages/PublicPlans";
import { Disclosures, Privacy, Terms } from "@/app/pages/Legal";

const Today = lazy(() => import("@/app/pages/Today"));
const XrayPage = lazy(() => import("@/app/pages/XrayPage"));
const Verdicts = lazy(() => import("@/app/pages/Verdicts"));
const CoinPage = lazy(() => import("@/app/pages/CoinPage"));
const MyPlan = lazy(() => import("@/app/pages/MyPlan"));
const Airdrops = lazy(() => import("@/app/pages/Airdrops"));
const Autopilot = lazy(() => import("@/app/pages/Autopilot"));
const ChartReader = lazy(() => import("@/app/pages/ChartReader"));
const Ask = lazy(() => import("@/app/pages/Ask"));
const Baskets = lazy(() => import("@/app/pages/Baskets"));
const Radar = lazy(() => import("@/app/pages/Radar"));
const Calendar = lazy(() => import("@/app/pages/Calendar"));
const P2P = lazy(() => import("@/app/pages/P2P"));
const News = lazy(() => import("@/app/pages/News"));
const Inbox = lazy(() => import("@/app/pages/Inbox"));
const Account = lazy(() => import("@/app/pages/Account"));
const AppPlans = lazy(() => import("@/app/pages/AppPlans"));
const AdminApp = lazy(() => import("@/app/admin/AdminApp"));
const AdminLogin = lazy(() => import("@/app/admin/AdminLogin"));

const fallback = <div className="min-h-[40vh] grid place-items-center"><Spinner /></div>;

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <ConfirmProvider>
          <GateSheet />
          <Suspense fallback={fallback}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/plans" element={<PublicPlans />} />
              <Route path="/terms" element={<Terms />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/disclosures" element={<Disclosures />} />

              <Route path="/app" element={<RequireAuth><AppShell /></RequireAuth>}>
                <Route index element={<Today />} />
                <Route path="xray" element={<XrayPage />} />
                <Route path="verdicts" element={<Verdicts />} />
                <Route path="coin/:symbol" element={<CoinPage />} />
                <Route path="plan" element={<MyPlan />} />
                <Route path="airdrops" element={<Airdrops />} />
                <Route path="autopilot" element={<Autopilot />} />
                <Route path="chart" element={<ChartReader />} />
                <Route path="ask" element={<Ask />} />
                <Route path="baskets" element={<Baskets />} />
                <Route path="radar" element={<Radar />} />
                <Route path="calendar" element={<Calendar />} />
                <Route path="p2p" element={<P2P />} />
                <Route path="news" element={<News />} />
                <Route path="inbox" element={<Inbox />} />
                <Route path="account" element={<Account />} />
                <Route path="plans" element={<AppPlans />} />
                <Route path="*" element={<Navigate to="/app" replace />} />
              </Route>

              <Route path="/admin/login" element={<AdminLogin />} />
              <Route path="/admin/*" element={<AdminApp />} />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
          </ConfirmProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
