/**
 * Record detail layout (DESIGN-04), shared by every P1 detail page: a header with the ID (mono),
 * title, breadcrumb slot and status; an optional workflow bar; URL-addressable tabs
 * (`?tab=history`); and a collapsible right rail for comments, approvals and attachments.
 *
 * Tabs are uncontrolled by default and read and write `?tab=` with `history.replaceState`. A page
 * on TanStack Router should pass `tab` and `onTabChange` from its validated search instead.
 * Superseded records stay visible with a "Superseded" chip and a link to the replacement.
 */
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "../components/button";
import type { IconName } from "../components/icon";
import { StatusChip } from "../components/status-chip";
import { cn } from "../lib/cn";
import type { Translate } from "../register/types";
import type { StatusTone } from "../tokens/tokens";
import { WorkflowBar, type WorkflowBarProps } from "./WorkflowBar";

export const DEFAULT_RECORD_TABS = ["details", "linked", "documents", "history"] as const;

const defaultTabKeys: Record<string, string> = {
  details: "ui.record.tab.details",
  linked: "ui.record.tab.linked",
  documents: "ui.record.tab.documents",
  history: "ui.record.tab.history",
};

export interface RecordTab {
  id: string;
  /** Required unless `id` is one of DEFAULT_RECORD_TABS. */
  labelKey?: string;
  content: ReactNode;
}

export interface RecordStatus {
  tone: StatusTone;
  icon: IconName;
  labelKey: string;
}

export interface RecordRail {
  comments?: ReactNode;
  approvals?: ReactNode;
  attachments?: ReactNode;
}

export interface RecordDetailProps {
  id: string;
  /** The record's own title (data, not a label). */
  title: string;
  /** Breadcrumb slot (the asset path later). */
  breadcrumb?: ReactNode;
  status: RecordStatus;
  workflow?: Omit<WorkflowBarProps, "translate">;
  tabs: readonly RecordTab[];
  rightRail?: RecordRail;
  actions?: ReactNode;
  superseded?: { byId: string; href: string };
  /** Controlled tab id (with `onTabChange`); omit both to keep the tab in `?tab=` directly. */
  tab?: string;
  onTabChange?: (tab: string) => void;
  /** Session key for the rail's open/closed state (default: one state for all detail pages). */
  railKey?: string;
  translate: Translate;
}

const railSlots = [
  ["comments", "ui.record.rail.comments"],
  ["approvals", "ui.record.rail.approvals"],
  ["attachments", "ui.record.rail.attachments"],
] as const;

function readUrlTab(): string | null {
  return typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("tab");
}

function writeUrlTab(tab: string) {
  const url = new URL(window.location.href);
  url.searchParams.set("tab", tab);
  window.history.replaceState(window.history.state, "", url);
}

function readRail(key: string): boolean {
  try {
    return sessionStorage.getItem(key) !== "closed";
  } catch {
    return true;
  }
}

function writeRail(key: string, open: boolean) {
  try {
    sessionStorage.setItem(key, open ? "open" : "closed");
  } catch {
    // Storage blocked (private mode): the rail still toggles for this page view.
  }
}

export function RecordDetail({
  id,
  title,
  breadcrumb,
  status,
  workflow,
  tabs,
  rightRail,
  actions,
  superseded,
  tab,
  onTabChange,
  railKey = "default",
  translate,
}: RecordDetailProps) {
  const baseId = useId();
  const [urlTab, setUrlTab] = useState(readUrlTab);
  const requested = tab ?? urlTab;
  const selected = tabs.find((t) => t.id === requested) ?? tabs[0];
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());

  const storageKey = `aip.record.rail.${railKey}`;
  const [railOpen, setRailOpen] = useState(() => readRail(storageKey));

  const select = (next: string) => {
    if (tab !== undefined || onTabChange) {
      onTabChange?.(next);
    } else {
      setUrlTab(next);
      writeUrlTab(next);
    }
  };

  const onTabKey = (event: KeyboardEvent) => {
    const at = tabs.findIndex((t) => t.id === selected?.id);
    const to =
      event.key === "ArrowRight"
        ? (at + 1) % tabs.length
        : event.key === "ArrowLeft"
          ? (at - 1 + tabs.length) % tabs.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? tabs.length - 1
              : -1;
    const next = tabs[to];
    if (!next) return;
    event.preventDefault();
    select(next.id);
    tabRefs.current.get(next.id)?.focus();
  };

  const tabLabel = (t: RecordTab) => translate(t.labelKey ?? defaultTabKeys[t.id] ?? t.id);
  const railId = `${baseId}-rail`;
  const rail = rightRail && railSlots.some(([slot]) => rightRail[slot] !== undefined) ? rightRail : undefined;

  return (
    <div className={cn("aip-record", rail && railOpen && "aip-record--rail-open")}>
      <header className="aip-record__header">
        {breadcrumb && <div className="aip-record__breadcrumb">{breadcrumb}</div>}
        <div className="aip-record__heading">
          <span className="aip-record__id">{id}</span>
          <h1 className="aip-record__title">{title}</h1>
          <StatusChip tone={status.tone} icon={status.icon} label={translate(status.labelKey)} />
          {superseded && (
            <>
              <StatusChip tone="neutral" icon="minus" label={translate("ui.record.superseded")} />
              <a className="aip-record__superseded-link" href={superseded.href}>
                {translate("ui.record.supersededBy", { id: superseded.byId })}
              </a>
            </>
          )}
        </div>
        {(actions || rail) && (
          <div className="aip-record__actions">
            {actions}
            {rail && (
              <Button
                variant="ghost"
                aria-expanded={railOpen}
                aria-controls={railId}
                onClick={() => {
                  writeRail(storageKey, !railOpen);
                  setRailOpen(!railOpen);
                }}
              >
                {translate(railOpen ? "ui.record.rail.hide" : "ui.record.rail.show")}
              </Button>
            )}
          </div>
        )}
      </header>
      {workflow && <WorkflowBar {...workflow} translate={translate} />}
      <div className="aip-record__body">
        <div className="aip-record__main">
          <div className="aip-record__tabs" role="tablist" aria-label={translate("ui.record.tabs")}>
            {tabs.map((t) => {
              const active = t.id === selected?.id;
              return (
                <button
                  key={t.id}
                  ref={(el) => {
                    if (el) tabRefs.current.set(t.id, el);
                    else tabRefs.current.delete(t.id);
                  }}
                  type="button"
                  role="tab"
                  id={`${baseId}-tab-${t.id}`}
                  aria-selected={active}
                  aria-controls={`${baseId}-panel-${t.id}`}
                  tabIndex={active ? 0 : -1}
                  className="aip-record__tab"
                  onClick={() => select(t.id)}
                  onKeyDown={onTabKey}
                >
                  {tabLabel(t)}
                </button>
              );
            })}
          </div>
          {tabs.map((t) => (
            // Every panel exists so each tab's aria-controls resolves; only the selected one renders content.
            <div
              key={t.id}
              role="tabpanel"
              id={`${baseId}-panel-${t.id}`}
              aria-labelledby={`${baseId}-tab-${t.id}`}
              hidden={t.id !== selected?.id}
              tabIndex={0}
              className="aip-record__panel"
            >
              {t.id === selected?.id && t.content}
            </div>
          ))}
        </div>
        {rail && (
          <aside id={railId} className="aip-record__rail" aria-label={translate("ui.record.rail")} hidden={!railOpen}>
            {railOpen &&
              railSlots.map(([slot, key]) =>
                rail[slot] === undefined ? null : (
                  <section key={slot} className="aip-record__rail-section" aria-labelledby={`${baseId}-rail-${slot}`}>
                    <h2 id={`${baseId}-rail-${slot}`} className="aip-record__rail-title">
                      {translate(key)}
                    </h2>
                    {rail[slot]}
                  </section>
                ),
              )}
          </aside>
        )}
      </div>
    </div>
  );
}

