// In-app confirmation, in the app's own sheet instead of the browser's confirm() box (QA 10 Nov).
//
//   const confirm = useConfirm();
//   if (!(await confirm({ title: "Delete this plan?", body: "…", confirmLabel: "Delete plan", danger: true }))) return;
//
// One <ConfirmProvider> wraps the app (App.js). The action button says exactly what happens ("Delete plan"), and
// Cancel or closing the sheet resolves false.
import { createContext, useCallback, useContext, useRef, useState } from "react";
import { Button, Sheet } from "./ui";

const Ctx = createContext(null);

export function ConfirmProvider({ children }) {
  const [req, setReq] = useState(null);         // {title, body, confirmLabel, cancelLabel, danger}
  const resolver = useRef(null);

  const confirm = useCallback((opts) => new Promise((resolve) => {
    resolver.current?.(false);                   // a second request replaces an open one
    resolver.current = resolve;
    setReq(opts || {});
  }), []);

  const close = (answer) => {
    resolver.current?.(answer);
    resolver.current = null;
    setReq(null);
  };

  return (
    <Ctx.Provider value={confirm}>
      {children}
      <Sheet open={!!req} onClose={() => close(false)} title={req?.title || "Are you sure?"}>
        {req && (
          <div className="space-y-5" data-testid="confirm-sheet">
            {req.body && <p className="text-[16px] leading-relaxed">{req.body}</p>}
            <div className="flex flex-col-reverse sm:flex-row gap-2">
              <Button variant="secondary" className="sm:flex-1" onClick={() => close(false)} data-testid="confirm-cancel">{req.cancelLabel || "Cancel"}</Button>
              <Button variant={req.danger ? "danger" : "primary"} className="sm:flex-1" onClick={() => close(true)} data-testid="confirm-ok" autoFocus>
                {req.confirmLabel || "Confirm"}
              </Button>
            </div>
          </div>
        )}
      </Sheet>
    </Ctx.Provider>
  );
}

export function useConfirm() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useConfirm must be used inside <ConfirmProvider>");
  return c;
}
