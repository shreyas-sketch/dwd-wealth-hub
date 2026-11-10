// SIP Autopilot pieces shared by /app/autopilot and Baskets: schedule fields, plan card, venue picker.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { dtime, inr, sdate, usd, venueName, WEEKDAYS } from "@/lib/format";
import { Button, Chip, Field, Segmented, Select, Stat } from "./ui";
import { Move } from "./common";
import { useConfirm } from "./Confirm";

export const FREQ_LABEL = { weekly: "Every week", monthly: "Every month" };

export function scheduleText(p) {
  if (p.frequency === "weekly") return `every ${WEEKDAYS[p.weekday ?? 0] || "week"}`;
  if (p.frequency === "monthly") return `on day ${p.day ?? 1} of each month`;
  return p.frequency || "";
}

// frequency + weekday / day-of-month
export function ScheduleFields({ value, onChange, frequencies = ["monthly"] }) {
  const freqs = (frequencies || []).length ? frequencies : ["monthly"];
  return (
    <div className="space-y-3">
      <Field label="How often">
        <Segmented options={freqs.map((f) => ({ value: f, label: FREQ_LABEL[f] || f }))} value={value.frequency} onChange={(v) => onChange({ ...value, frequency: v })} label="Frequency" testid="dca-frequency" />
      </Field>
      {value.frequency === "weekly" ? (
        <Field label="On">
          <Select value={value.weekday ?? 0} onChange={(e) => onChange({ ...value, weekday: Number(e.target.value) })} data-testid="dca-weekday">
            {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
          </Select>
        </Field>
      ) : (
        <Field label="Day of the month">
          <Select value={value.day ?? 1} onChange={(e) => onChange({ ...value, day: Number(e.target.value) })} data-testid="dca-day">
            {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{d}</option>)}
          </Select>
        </Field>
      )}
    </div>
  );
}

export function scheduleBody(v) {
  return v.frequency === "weekly" ? { frequency: "weekly", weekday: v.weekday ?? 0 } : { frequency: v.frequency || "monthly", day: v.day ?? 1 };
}

export function VenuePicker({ venues, value, onChange }) {
  const linked = (venues || []).filter((v) => v.linked);
  if (!linked.length) return <p className="text-[14px] text-bz-miss">Link an exchange first.</p>;
  return (
    <Field label="From my exchange">
      <Segmented options={linked.map((v) => ({ value: v.venue, label: venueName(v.venue) }))} value={value} onChange={onChange} label="Exchange" testid="dca-venue" />
    </Field>
  );
}

export function DcaPlanCard({ p, basketName }) {
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const act = async (kind) => {
    setErr(""); setBusy(kind);
    try {
      if (kind === "delete") {
        if (!(await confirm({ title: "Stop and delete this Autopilot?", danger: true, confirmLabel: "Delete Autopilot",
          body: "No more buys will happen. Coins already bought stay in your exchange account." }))) { setBusy(null); return; }
        await api.delete(`/autopilot/plan/${p.id}`);
      } else {
        await api.post(`/autopilot/plan/${p.id}/${kind}`);
      }
      qc.invalidateQueries({ queryKey: ["autopilot"] });
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };
  const active = p.status === "active";
  const title = p.kind === "basket" ? (basketName || "Basket") : p.coin;
  return (
    <div className="rounded-bzcard border border-bz-line bg-bz-card p-4" data-testid={`dca-plan-${p.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[17px] font-semibold">{inr(p.amount_inr)} into {title}</p>
          <p className="text-[13px] text-bz-muted">{scheduleText(p)} · {venueName(p.venue)}{p.kind === "basket" ? " · basket" : ""}</p>
        </div>
        <Chip tone={active ? "bull" : "muted"}>{active ? "Active" : "Paused"}</Chip>
      </div>
      {active && p.next_at && <p className="text-[13px] mt-2">Next buy: <b>{dtime(p.next_at)}</b></p>}
      {p.last_error && <p className="text-[13px] mt-2 rounded-bzbtn bg-bz-miss-tint text-bz-miss px-3 py-2">{p.last_error}</p>}
      <div className="grid grid-cols-3 gap-2 mt-3">
        <Stat label="Put in" value={inr(p.invested_inr)} sub={`${p.buys ?? 0} buys`} />
        <Stat label="Worth" value={inr(p.value_inr)} />
        <Stat label="Return" value={<Move v={p.return_pct} />} />
      </div>
      {(p.recent || []).length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[13px] font-semibold text-bz-muted py-1">Recent buys</summary>
          <ul className="mt-1 divide-y divide-bz-line text-[13px]">
            {p.recent.map((r, i) => (
              <li key={`${r.at}-${i}`} className="py-1.5 flex justify-between gap-2">
                <span>{sdate(r.at)} · {r.coin}</span>
                <span className="tabular text-bz-muted">{inr(r.inr)} · {Number(r.qty || 0).toLocaleString("en-IN", { maximumFractionDigits: 6 })} @ {usd(r.price_usd)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="flex flex-wrap gap-2 mt-3">
        {active ? <Button variant="small" onClick={() => act("pause")} loading={busy === "pause"} data-testid="dca-pause">Pause</Button>
          : <Button variant="small" onClick={() => act("resume")} loading={busy === "resume"} data-testid="dca-resume">Resume</Button>}
        <Button variant="small" className="text-bz-miss" onClick={() => act("delete")} loading={busy === "delete"} data-testid="dca-delete">Delete</Button>
      </div>
      {err && <p className="text-sm text-bz-miss mt-2" role="alert">{err}</p>}
    </div>
  );
}

