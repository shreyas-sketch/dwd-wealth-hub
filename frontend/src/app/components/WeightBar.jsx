// Stacked horizontal bar of weights (allocation, basket coins) with a legend.
import { SERIES } from "./chart";

export default function WeightBar({ items = [], labelKey = "symbol", valueKey = "pct" }) {
  const rows = (items || []).filter((i) => Number(i?.[valueKey]) > 0);
  if (!rows.length) return null;
  const total = rows.reduce((s, i) => s + Number(i[valueKey]), 0) || 100;
  return (
    <div>
      <div className="h-3.5 rounded-full overflow-hidden flex bg-bz-inset" role="img"
        aria-label={rows.map((i) => `${i[labelKey]} ${i[valueKey]}%`).join(", ")}>
        {rows.map((i, n) => (
          <div key={`${i[labelKey]}-${n}`} style={{ width: `${(Number(i[valueKey]) / total) * 100}%`, background: SERIES[n % SERIES.length] }}
            className="h-full border-r-2 border-bz-card last:border-r-0" />
        ))}
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5 text-[13px]">
        {rows.map((i, n) => (
          <li key={`${i[labelKey]}-${n}`} className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-[3px]" style={{ background: SERIES[n % SERIES.length] }} aria-hidden />
            <span className="font-semibold">{i[labelKey]}</span>
            <span className="text-bz-muted tabular">{Number(i[valueKey])}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
