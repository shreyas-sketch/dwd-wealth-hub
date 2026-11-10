// One sentence about what a new account gets, built from the live trial length (Admin › Settings › Trial days),
// so every sign-up prompt says the same true thing (QA 10 Nov: the copy said "free account" while new users get
// every tool on a trial first).
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useTrialDays() {
  const q = useQuery({ queryKey: ["plans-catalog"], queryFn: async () => (await api.get("/plans/catalog")).data, staleTime: 10 * 60_000 });
  const d = Number(q.data?.trial_days);
  return Number.isFinite(d) ? d : null;
}

// "Every tool free for 3 days, then the free plan." / "A free account." when there is no trial.
export function newAccountLine(days) {
  if (days > 0) return `New accounts get every tool free for ${days} day${days === 1 ? "" : "s"}, then the free plan. No card needed.`;
  return "New accounts start on the free plan. No card needed.";
}

export function signupLabel(days) {
  return days > 0 ? `Start your ${days}-day free trial` : "Create your free account";
}
