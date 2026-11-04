// Bitcoin's 4-year halving cycle drawn as a dial: the ring starts at the last halving (top) and closes at the
// next one. The saffron arc is the time already passed; the hand is today. The four phase segments use the same
// month boundaries as the server (features/verdicts.py cycle()): build-up < 6 months, expansion < 18,
// late cycle < 30, then cool-off.
//
// This is the dashboard's one bold element. Its only motion is the hand sweeping from the halving to today on
// load (skipped when the person prefers reduced motion).
import { monthLabel, usd } from "@/lib/format";

export const PHASES = [
  { key: "build", name: "Build-up", from: 0, to: 6 },
  { key: "expansion", name: "Expansion", from: 6, to: 18 },
  { key: "late", name: "Late cycle", from: 18, to: 30 },
  { key: "cool", name: "Cool-off", from: 30, to: Infinity },
];
const MONTH = 30.44;

export function phaseIndex(daysSince) {
  const m = (Number(daysSince) || 0) / MONTH;
  return PHASES.findIndex((p) => m >= p.from && m < p.to);
}

const SIZE = 240;
const C = SIZE / 2;
const R = 96;
const STROKE = 16;
const CIRC = 2 * Math.PI * R;

// Arc from fraction a to b of the circle, starting at 12 o'clock, clockwise.
function arcPath(a, b) {
  const pt = (f) => {
    const t = f * 2 * Math.PI - Math.PI / 2;
    return [C + R * Math.cos(t), C + R * Math.sin(t)];
  };
  const [x1, y1] = pt(a);
  const [x2, y2] = pt(b);
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 ${b - a > 0.5 ? 1 : 0} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

function Dial({ since, total, pos }) {
  const spanMonths = total / MONTH;
  const gap = 0.006;
  const segs = PHASES.map((p) => [p.from / spanMonths, Math.min(1, p.to / spanMonths)]);
  const done = Math.max(0, Math.min(1, pos));
  const turn = done * 360;
  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-[188px] sm:w-[220px] lg:w-[240px] h-auto shrink-0" role="img"
      aria-label={`Day ${since.toLocaleString("en-IN")} of about ${total.toLocaleString("en-IN")} in the 4-year Bitcoin cycle`}>
      {/* phase segments (the road ahead) */}
      {segs.map(([a, b], i) => (
        <path key={PHASES[i].key} d={arcPath(a + gap, Math.max(a + gap, b - gap))} fill="none"
          stroke="var(--bz-hero-line)" strokeWidth={STROKE} strokeLinecap="butt" />
      ))}
      {/* time already passed since the halving */}
      <circle cx={C} cy={C} r={R} fill="none" stroke="var(--bz-gold)" strokeWidth={STROKE} strokeLinecap="round"
        transform={`rotate(-90 ${C} ${C})`} strokeDasharray={CIRC} className="cz-sweep"
        style={{ "--cz-arc-len": CIRC, "--cz-arc-off": CIRC * (1 - done), strokeDashoffset: CIRC * (1 - done) }} />
      {/* halving mark at 12 o'clock: where this cycle began and the next one starts */}
      <line x1={C} y1={C - R - STROKE / 2 - 8} x2={C} y2={C - R + STROKE / 2 + 2} stroke="var(--bz-hero-ink)" strokeWidth="3" strokeLinecap="round" />
      {/* today */}
      <g className="cz-hand" style={{ "--cz-turn": `${turn}deg`, transformBox: "view-box", transformOrigin: "center" }}>
        <circle cx={C} cy={C - R} r={STROKE / 2 + 5} fill="var(--bz-hero)" />
        <circle cx={C} cy={C - R} r={STROKE / 2 + 1} fill="var(--bz-hero-ink)" />
      </g>
      <text x={C} y={C - 6} textAnchor="middle" className="font-bzdisplay" fill="var(--bz-hero-ink)" fontSize="44" fontWeight="700">
        {since.toLocaleString("en-IN")}
      </text>
      <text x={C} y={C + 22} textAnchor="middle" className="font-bz" fill="var(--bz-hero-muted)" fontSize="15">
        days since the halving
      </text>
    </svg>
  );
}

export default function CycleDial({ cycle }) {
  if (!cycle || cycle.days_since == null) return null;
  const since = Number(cycle.days_since) || 0;
  const toNext = Number(cycle.days_to_next) || 0;
  const total = since + toNext || 1456;
  const pos = cycle.position_pct != null ? Number(cycle.position_pct) / 100 : since / total;
  const idx = phaseIndex(since);
  return (
    <section className="rounded-bzhero bg-bz-hero text-bz-hero-ink px-5 py-6 sm:px-8 sm:py-8" data-testid="cycle-dial" aria-labelledby="cycle-title">
      <div className="flex flex-col md:flex-row md:items-center gap-6 md:gap-10">
        <Dial since={since} total={total} pos={pos} />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] text-bz-hero-muted">Where Bitcoin is in its 4-year cycle</p>
          <h2 id="cycle-title" className="font-bzdisplay text-[31px] sm:text-[39px] font-bold leading-[1.05] mt-1">{cycle.phase || PHASES[idx]?.name}</h2>
          {cycle.phase_note && <p className="text-[16px] leading-relaxed text-bz-hero-muted mt-3 max-w-[58ch]">{cycle.phase_note}</p>}
          <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 max-w-[480px]">
            <div>
              <dt className="text-[14px] text-bz-hero-muted">Next halving</dt>
              <dd className="font-bzdisplay text-[22px] font-semibold leading-tight tabular">
                {toNext.toLocaleString("en-IN")} days
                {cycle.next_halving_est && <span className="block font-bz text-[14px] font-normal text-bz-hero-muted">around {monthLabel(cycle.next_halving_est)}</span>}
              </dd>
            </div>
            {cycle.drawdown_from_ath_pct != null && (
              <div>
                <dt className="text-[14px] text-bz-hero-muted">From its all-time high</dt>
                <dd className="font-bzdisplay text-[22px] font-semibold leading-tight tabular">
                  {Math.abs(Number(cycle.drawdown_from_ath_pct)).toFixed(1)}% below
                  {cycle.ath_usd != null && <span className="block font-bz text-[14px] font-normal text-bz-hero-muted">high was {usd(cycle.ath_usd)}</span>}
                </dd>
              </div>
            )}
          </dl>
        </div>
      </div>
      {/* the cycle is a real sequence, so it is shown as one, with today's phase marked */}
      <ol className="mt-7 pt-5 border-t border-bz-hero-line grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-3" aria-label="The four phases">
        {PHASES.map((p, i) => {
          const now = i === idx;
          return (
            <li key={p.key} className={now ? "" : "opacity-70"} aria-current={now ? "step" : undefined}>
              <span className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${now ? "bg-bz-gold" : i < idx ? "bg-bz-hero-ink" : "border border-bz-hero-muted"}`} aria-hidden />
                <span className={`text-[15px] font-semibold ${now ? "text-bz-gold" : ""}`}>{p.name}</span>
              </span>
              <span className="block text-[13px] leading-snug text-bz-hero-muted mt-0.5 pl-[18px]">
                {p.to === Infinity ? `From month ${p.from}` : `Months ${p.from}–${p.to}`}
              </span>
            </li>
          );
        })}
      </ol>
      {cycle.last_halving && <p className="text-[13px] text-bz-hero-muted mt-4">The last halving was in {monthLabel(cycle.last_halving)}.</p>}
    </section>
  );
}
