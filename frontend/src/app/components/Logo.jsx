import brand from "@/brand";

export function LogoMark({ size = 32, className = "" }) {
  return <img src="/logo.svg" alt="" width={size} height={size} className={`shrink-0 ${className}`} />;
}

export default function Logo({ className = "", word = "", big = false }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <LogoMark size={big ? 40 : 32} />
      <span className={`font-bzserif font-semibold tracking-[-0.01em] text-bz-ink whitespace-nowrap ${big ? "text-[24px]" : "text-[19px]"} ${word}`}>{brand.name}</span>
    </span>
  );
}
