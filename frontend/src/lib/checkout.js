// Checkout (API_CONTRACT.md › Billing):
//   POST /billing/checkout {plan} → mode "razorpay": open Razorpay with subscription_id + key, then POST /billing/verify
//                                 → mode "fake": POST /billing/verify {subscription_id, payment_id: "pay_fake", signature: "fake"}
// then refresh /auth/me.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "./api";
import { track } from "./attribution";
import { useAuth } from "@/context/AuthContext";
import brand from "@/brand";

let rzpPromise = null;
function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  if (!rzpPromise) {
    rzpPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://checkout.razorpay.com/v1/checkout.js";
      s.onload = resolve;
      s.onerror = () => { rzpPromise = null; reject(new Error("Could not load the payment window. Check your internet.")); };
      document.body.appendChild(s);
    });
  }
  return rzpPromise;
}

export function useCheckout() {
  const { refreshMe, setPlan } = useAuth();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);

  const buy = async (plan) => {
    setError(""); setDone(null); setBusy(plan);
    try {
      const co = (await api.post("/billing/checkout", { plan })).data || {};
      track("checkout_opened", { plan, mode: co.mode });
      let resp;
      if (co.mode === "razorpay") {
        await loadRazorpay();
        resp = await new Promise((resolve, reject) => {
          const r = new window.Razorpay({
            key: co.key_id || co.key,
            subscription_id: co.subscription_id,
            name: co.name || brand.name,
            description: co.plan ? `${co.plan === "pro" ? "₹5,000" : "₹2,000"} plan` : undefined,
            prefill: co.prefill || {},
            theme: { color: "#F08A0B" },
            handler: (r2) => resolve({
              subscription_id: r2.razorpay_subscription_id || co.subscription_id,
              payment_id: r2.razorpay_payment_id,
              signature: r2.razorpay_signature,
            }),
            modal: { ondismiss: () => reject(new Error("dismissed")) },
          });
          r.open();
        });
      } else {
        resp = { subscription_id: co.subscription_id, payment_id: "pay_fake", signature: "fake" };
      }
      const v = (await api.post("/billing/verify", resp)).data || {};
      if (v.plan) setPlan(v.plan);
      await refreshMe();
      qc.invalidateQueries();
      setDone(v.plan || { plan });
      return true;
    } catch (e) {
      if (e?.message !== "dismissed") setError(e?.response ? apiError(e, "Payment did not go through.") : e?.message || "Payment did not go through.");
      return false;
    } finally {
      setBusy(null);
    }
  };
  return { buy, busy, error, done };
}
