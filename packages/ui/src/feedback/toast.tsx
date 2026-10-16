/**
 * Non-blocking toasts (DESIGN-04): the replacement for `window.alert`.
 *
 *   <Toaster translate={t} />                     // once, near the app root
 *   toast.success("projects.saved", { code });    // anywhere, no hook needed
 *
 * Success and info sit in an `aria-live="polite"` region and leave after 5 s, restarting the
 * 5 s when the pointer or focus leaves them. Errors sit in an `assertive` region and stay until
 * dismissed. At most three show at once (the newest); older ones return as newer ones leave.
 */
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { Button } from "../components/button";
import { Icon, type IconName } from "../components/icon";
import { cn } from "../lib/cn";
import type { Translate } from "../register/types";

export const TOAST_TIMEOUT_MS = 5000;
export const MAX_VISIBLE_TOASTS = 3;

type ToastKind = "success" | "info" | "error";
type Params = Record<string, string | number>;

export interface ToastAction {
  labelKey: string;
  onSelect: () => void;
}

export interface ToastOptions {
  action?: ToastAction;
}

interface ToastItem {
  id: number;
  kind: ToastKind;
  messageKey: string;
  params?: Params;
  action?: ToastAction;
}

let items: readonly ToastItem[] = [];
let seq = 0;
const listeners = new Set<() => void>();

function emit(next: readonly ToastItem[]) {
  items = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function push(kind: ToastKind) {
  return (messageKey: string, params?: Params, options: ToastOptions = {}): number => {
    const id = ++seq;
    emit([...items, { id, kind, messageKey, ...(params ? { params } : {}), ...(options.action ? { action: options.action } : {}) }]);
    return id;
  };
}

export const toast = {
  success: push("success"),
  info: push("info"),
  error: push("error"),
  dismiss(id: number) {
    emit(items.filter((item) => item.id !== id));
  },
  /** Removes every toast (tests, sign-out). */
  clear() {
    emit([]);
  },
};

const icons: Record<ToastKind, IconName> = { success: "success", info: "info", error: "alert" };

export interface ToasterProps {
  translate: Translate;
}

export function Toaster({ translate }: ToasterProps) {
  const all = useSyncExternalStore(subscribe, () => items, () => items);
  const visible = all.slice(-MAX_VISIBLE_TOASTS);
  const render = (kind: (k: ToastKind) => boolean) =>
    visible.filter((item) => kind(item.kind)).map((item) => <ToastView key={item.id} item={item} translate={translate} />);

  // Plain live regions, not role=status/alert: they are always mounted (so screen readers watch
  // them before the first toast) and must not be mistaken for a page's own status or alert.
  return (
    <section className="aip-toaster" aria-label={translate("ui.toast.region")}>
      <div className="aip-toaster__stack" aria-live="polite">
        {render((k) => k !== "error")}
      </div>
      <div className="aip-toaster__stack" aria-live="assertive">
        {render((k) => k === "error")}
      </div>
    </section>
  );
}

function ToastView({ item, translate }: { item: ToastItem; translate: Translate }) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const persistent = item.kind === "error";
  const dismiss = useCallback(() => toast.dismiss(item.id), [item.id]);

  useEffect(() => {
    if (persistent || hovered || focused) return;
    const timer = setTimeout(dismiss, TOAST_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [persistent, hovered, focused, dismiss]);

  return (
    // The pointer and focus handlers only pause the timer; the toast's controls are real buttons.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <div
      className={cn("aip-toast", `aip-toast--${item.kind}`)}
      data-kind={item.kind}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false);
      }}
    >
      <Icon name={icons[item.kind]} />
      <p className="aip-toast__message">{translate(item.messageKey, item.params)}</p>
      {item.action && (
        <Button
          variant="secondary"
          onClick={() => {
            item.action?.onSelect();
            dismiss();
          }}
        >
          {translate(item.action.labelKey)}
        </Button>
      )}
      <Button variant="ghost" size="icon" aria-label={translate("ui.toast.dismiss")} onClick={dismiss}>
        <Icon name="close" />
      </Button>
    </div>
  );
}
