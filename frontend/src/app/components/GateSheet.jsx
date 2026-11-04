// One global sheet for API 403 "locked" and 402 "limit" answers (lib/api.js emits the event).
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { GATE_EVENT } from "@/lib/api";
import { Sheet } from "./ui";
import { LockCard } from "./common";

export default function GateSheet() {
  const [gate, setGate] = useState(null);
  const { pathname } = useLocation();
  useEffect(() => {
    const on = (e) => setGate(e.detail || null);
    window.addEventListener(GATE_EVENT, on);
    return () => window.removeEventListener(GATE_EVENT, on);
  }, []);
  useEffect(() => { setGate(null); }, [pathname]);
  if (!gate) return null;
  const limit = gate.code === "limit";
  return (
    <Sheet open onClose={() => setGate(null)} title={limit ? "Monthly limit reached" : "Upgrade to unlock"}>
      <LockCard feature={gate.feature} planNeeded={gate.plan_needed} kind={limit ? "limit" : "locked"}
        used={gate.used} limit={gate.limit} msg={gate.msg} onAction={() => setGate(null)} />
    </Sheet>
  );
}
