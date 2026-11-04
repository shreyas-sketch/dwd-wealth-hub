import brand from "@/brand";

export function LogoMark({ size = 32, className = "" }) {
  return <img src="/logo.svg" alt="" width={size} height={size} className={`shrink-0 ${className}`} />;
}

// onHero: wordmark in the light hero ink, for use on the indigo panel.
export default function Logo({ className = "", word = "", big = false, onHero = false }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <LogoMark size={big ? 40 : 32} />
      <span className={`font-bzdisplay font-bold tracking-[-0.01em] ${onHero ? "text-bz-hero-ink" : "text-bz-ink"} whitespace-nowrap ${big ? "text-[26px]" : "text-[21px]"} ${word}`}>{brand.name}</span>
    </span>
  );
}
