// Recharts styling that follows the theme tokens (SVG attributes accept var()).
export const AXIS_TICK = { fontSize: 11, fill: "var(--bz-muted)" };
export const TOOLTIP = {
  contentStyle: {
    background: "var(--bz-card)", border: "1px solid var(--bz-line)", borderRadius: 10,
    color: "var(--bz-ink)", fontSize: 13, boxShadow: "var(--card-shadow)",
  },
  labelStyle: { color: "var(--bz-muted)", fontSize: 12, marginBottom: 4 },
  itemStyle: { color: "var(--bz-ink)" },
  cursor: { stroke: "var(--bz-line-strong)", strokeDasharray: "3 3" },
};
export const C = {
  accent: "var(--bz-accent)",
  miss: "var(--bz-miss)",
  gold: "var(--bz-gold)",
  muted: "var(--bz-muted)",
  line: "var(--bz-line)",
  ink: "var(--bz-ink)",
};
// Distinct fills for stacked weight bars (allocation, baskets).
export const SERIES = ["var(--bz-gold)", "var(--bz-accent)", "#5B7FD6", "#9B6BD6", "#2BA6B5", "#D65B8F", "var(--bz-muted)"];
