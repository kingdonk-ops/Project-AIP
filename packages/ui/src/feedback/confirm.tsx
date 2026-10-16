/**
 * Confirm dialog with a promise API (DESIGN-04): the replacement for `window.confirm`.
 *
 *   <ConfirmProvider translate={t}>…</ConfirmProvider>     // once, near the app root
 *   if (await confirm({ titleKey, bodyKey, confirmKey, tone: "danger" })) remove();
 *
 * `confirm()` never blocks: it opens the dialog and resolves `true` on Confirm and `false` on
 * Cancel, Escape or the close button. A second call while one is open resolves the first `false`.
 */
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "../components/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "../components/dialog";
import { Input } from "../components/input";
import { Label } from "../components/label";
import type { Translate } from "../register/types";

export interface ConfirmOptions {
  titleKey: string;
  bodyKey: string;
  confirmKey: string;
  /** Interpolation values for the title and body keys. */
  params?: Record<string, string | number>;
  /** `danger` styles Confirm as destructive and puts first focus on Cancel. */
  tone?: "default" | "danger";
  /** The user must type this exact text (e.g. the record code) before Confirm is enabled. */
  requireText?: string;
}

type Open = (options: ConfirmOptions) => Promise<boolean>;

interface Pending {
  id: number;
  options: ConfirmOptions;
  resolve: (value: boolean) => void;
}

let mounted: Open | null = null;
let requests = 0;

/** Opens the confirm dialog of the mounted `<ConfirmProvider>`. */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  if (!mounted) return Promise.reject(new Error("confirm() needs a mounted <ConfirmProvider>"));
  return mounted(options);
}

const ConfirmContext = createContext<Open>(confirm);

/** The provider's `confirm`, for components that prefer a hook. */
export function useConfirm(): Open {
  return useContext(ConfirmContext);
}

export interface ConfirmProviderProps {
  translate: Translate;
  children?: ReactNode;
}

export function ConfirmProvider({ translate, children }: ConfirmProviderProps) {
  const [pending, setPending] = useState<Pending | null>(null);
  const current = useRef<Pending | null>(null);

  const open = useCallback<Open>(
    (options) =>
      new Promise<boolean>((resolve) => {
        current.current?.resolve(false);
        const next = { id: ++requests, options, resolve };
        current.current = next;
        setPending(next);
      }),
    [],
  );

  useEffect(() => {
    mounted = open;
    return () => {
      if (mounted === open) mounted = null;
      current.current?.resolve(false);
      current.current = null;
    };
  }, [open]);

  const settle = useCallback((value: boolean) => {
    const request = current.current;
    if (!request) return;
    current.current = null;
    setPending(null);
    request.resolve(value);
  }, []);

  return (
    <ConfirmContext.Provider value={open}>
      {children}
      <Dialog open={pending !== null} onOpenChange={(isOpen) => !isOpen && settle(false)}>
        {pending && <ConfirmBody key={pending.id} pending={pending} settle={settle} translate={translate} />}
      </Dialog>
    </ConfirmContext.Provider>
  );
}

// `key={pending.id}` remounts the body per request, so typed text and focus start fresh.
function ConfirmBody({
  pending,
  settle,
  translate,
}: {
  pending: Pending;
  settle: (value: boolean) => void;
  translate: Translate;
}) {
  const { titleKey, bodyKey, confirmKey, params, tone = "default", requireText } = pending.options;
  const [typed, setTyped] = useState("");
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const blocked = requireText !== undefined && typed !== requireText;

  return (
    <DialogContent
      closeLabel={translate("ui.close")}
      className="aip-confirm"
      onOpenAutoFocus={(event) => {
        // Typing is the safe first step; otherwise a destructive question starts on Cancel.
        event.preventDefault();
        const target = requireText !== undefined ? inputRef : tone === "danger" ? cancelRef : confirmRef;
        target.current?.focus();
      }}
    >
      <DialogTitle>{translate(titleKey, params)}</DialogTitle>
      <DialogDescription>{translate(bodyKey, params)}</DialogDescription>
      <form
        className="aip-confirm__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!blocked) settle(true);
        }}
      >
        {requireText !== undefined && (
          <div className="aip-confirm__require">
            <Label htmlFor={inputId}>{translate("ui.confirm.requireText", { text: requireText })}</Label>
            <Input
              id={inputId}
              ref={inputRef}
              value={typed}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setTyped(event.target.value)}
            />
          </div>
        )}
        <div className="aip-confirm__actions">
          <Button ref={cancelRef} variant="secondary" onClick={() => settle(false)}>
            {translate("ui.confirm.cancel")}
          </Button>
          <Button ref={confirmRef} type="submit" variant={tone === "danger" ? "danger" : "primary"} disabled={blocked}>
            {translate(confirmKey, params)}
          </Button>
        </div>
      </form>
    </DialogContent>
  );
}
