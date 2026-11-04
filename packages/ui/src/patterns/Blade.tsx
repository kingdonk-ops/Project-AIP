/**
 * Blade (DESIGN-09 part B, was DESIGN-11): a right-hand slide-over for a record opened from a queue
 * or register row. Radix Dialog gives the modal focus trap; Escape and the close button close it and
 * focus returns to the element that had it when the blade opened (the row): Radix only restores a
 * `Dialog.Trigger`, and a blade is opened from a queue row or a URL, so the Blade remembers it.
 *
 * The open record lives in the URL as `?open=<id>` so the permalink and Back work. Apps with a router
 * pass `open`/`onOpenChange` from their own search state using `readBladeParam` / `writeBladeParam`;
 * `useBladeParam` does the same over `window.history` for pages without one.
 */
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "../components/icon";
import { StatusChip } from "../components/status-chip";
import type { Translate } from "../register/types";
import type { StatusTone } from "../tokens/tokens";

export const BLADE_PARAM = "open";

/** The open record id in a search string (`?open=ITP-0042`), or `null`. */
export function readBladeParam(search: string): string | null {
  const value = new URLSearchParams(search).get(BLADE_PARAM);
  return value ? value : null;
}

/** `search` with `?open=` set to `id`, or removed when `id` is `null`; keeps every other parameter. */
export function writeBladeParam(search: string, id: string | null): string {
  const params = new URLSearchParams(search);
  if (id) params.set(BLADE_PARAM, id);
  else params.delete(BLADE_PARAM);
  const next = params.toString();
  return next ? `?${next}` : "";
}

const PUSHED = "aip-blade";

/**
 * `?open=` over `window.history`: opening pushes an entry (so Back closes the blade), closing goes
 * back when this hook pushed the entry and otherwise replaces it. Follows Back/Forward via popstate.
 */
export function useBladeParam(): [string | null, (id: string | null) => void] {
  const [openId, setOpenId] = useState(() => readBladeParam(window.location.search));

  useEffect(() => {
    const onPop = () => setOpenId(readBladeParam(window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const set = useCallback((id: string | null) => {
    const { pathname, search, hash } = window.location;
    const url = `${pathname}${writeBladeParam(search, id)}${hash}`;
    if (id) {
      window.history.pushState({ [PUSHED]: true }, "", url);
    } else if ((window.history.state as Record<string, unknown> | null)?.[PUSHED]) {
      window.history.back();
    } else {
      window.history.replaceState(window.history.state, "", url);
    }
    setOpenId(id);
  }, []);

  return [openId, set];
}

export interface BladeStatus {
  tone: StatusTone;
  icon: IconName;
  labelKey: string;
}

export interface BladeBanner {
  tone: StatusTone;
  icon: IconName;
  /** Already translated text, e.g. an SLA escalation. */
  text: string;
}

export interface BladeProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The record's reference, shown in mono. */
  recordId: string;
  title: string;
  breadcrumb?: ReactNode;
  status?: BladeStatus;
  /** Full-page URL of the record; rendered as a link in the header. */
  permalink?: string;
  banner?: BladeBanner;
  /** Sticky action bar at the bottom. */
  actions?: ReactNode;
  children: ReactNode;
  translate: Translate;
}

export function Blade({
  open,
  onOpenChange,
  recordId,
  title,
  breadcrumb,
  status,
  permalink,
  banner,
  actions,
  children,
  translate,
}: BladeProps) {
  const returnTo = useRef<HTMLElement | null>(null);
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="aip-blade__overlay" />
        <DialogPrimitive.Content
          className="aip-blade"
          aria-describedby={undefined}
          data-record={recordId}
          onOpenAutoFocus={() => {
            // Runs before focus moves in, so this is the row (or body when opened from a URL).
            returnTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (returnTo.current?.isConnected) returnTo.current.focus();
          }}
        >
          <header className="aip-blade__header">
            <div className="aip-blade__heading">
              <span className="aip-blade__id">{recordId}</span>
              <DialogPrimitive.Title className="aip-blade__title">{title}</DialogPrimitive.Title>
              {breadcrumb && <div className="aip-blade__breadcrumb">{breadcrumb}</div>}
              <div className="aip-blade__meta">
                {status && <StatusChip tone={status.tone} icon={status.icon} label={translate(status.labelKey)} />}
                {permalink && (
                  <a className="aip-blade__permalink" href={permalink}>
                    {translate("ui.blade.permalink")}
                  </a>
                )}
              </div>
            </div>
            <DialogPrimitive.Close className="aip-dialog__close aip-blade__close" aria-label={translate("ui.close")}>
              <Icon name="close" />
            </DialogPrimitive.Close>
          </header>
          {banner && (
            <div className={`aip-blade__banner aip-blade__banner--${banner.tone}`} role="status">
              <Icon name={banner.icon} size={16} />
              <span>{banner.text}</span>
            </div>
          )}
          <div className="aip-blade__body">{children}</div>
          {actions && <div className="aip-blade__actions">{actions}</div>}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
