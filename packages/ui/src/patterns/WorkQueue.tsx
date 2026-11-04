/**
 * Work queue (DESIGN-09 part B, was DESIGN-11): a dense list of items awaiting the user, on the
 * register's column conventions (ID in mono, title with a snippet, asset path, due tag, status chip)
 * with up to three inline quick actions from the caller. Each row's main button (Tab, then Enter, or
 * a click) calls `onOpen(id)`, which the caller wires to the Blade. Overdue is always icon + text.
 */
import { useId, type KeyboardEvent } from "react";
import { Button } from "../components/button";
import { Icon, type IconName } from "../components/icon";
import { StatusChip } from "../components/status-chip";
import { cn } from "../lib/cn";
import type { Translate } from "../register/types";
import type { StatusTone } from "../tokens/tokens";

export const QUEUE_MAX_ACTIONS = 3;
const HOUR_MS = 3_600_000;

export interface WorkQueueAction {
  id: string;
  labelKey: string;
  onSelect: () => void;
}

export interface WorkQueueItem {
  id: string;
  title: string;
  snippet?: string;
  assetPath?: string;
  /** ISO timestamp the item is due. */
  due?: string;
  status: { tone: StatusTone; icon: IconName; labelKey: string };
  actions?: readonly WorkQueueAction[];
}

export interface WorkQueueTab {
  id: string;
  labelKey: string;
  count?: number;
}

export interface WorkQueueProps {
  items: readonly WorkQueueItem[];
  onOpen: (id: string) => void;
  /** Term key naming the list. */
  labelKey: string;
  translate: Translate;
  /** Clock for the due tags (tests pass a fixed time). */
  now?: Date;
  tabs?: readonly WorkQueueTab[];
  activeTab?: string;
  onTabChange?: (id: string) => void;
  /** Term key shown when there are no items. */
  emptyKey?: string;
}

export interface DueTag {
  overdue: boolean;
  key: string;
  params: Record<string, number>;
}

/** The due tag for `due` at `now`: whole hours under 48, whole days after; past due is overdue. */
export function dueTag(due: string, now: Date): DueTag {
  const diff = new Date(due).getTime() - now.getTime();
  const overdue = diff < 0;
  const hours = Math.max(1, Math.round(Math.abs(diff) / HOUR_MS));
  if (hours < 48) return { overdue, key: overdue ? "ui.queue.overdue" : "ui.queue.dueIn", params: { hours } };
  const days = Math.round(hours / 24);
  return { overdue, key: overdue ? "ui.queue.overdueDays" : "ui.queue.dueInDays", params: { days } };
}

function Due({ due, now, translate }: { due: string; now: Date; translate: Translate }) {
  const tag = dueTag(due, now);
  return (
    <span className={cn("aip-queue__due", tag.overdue && "aip-queue__due--overdue")}>
      <Icon name={tag.overdue ? "alert" : "clock"} size={14} />
      <time dateTime={due}>{translate(tag.key, tag.params)}</time>
    </span>
  );
}

export function WorkQueue({
  items,
  onOpen,
  labelKey,
  translate,
  now = new Date(),
  tabs,
  activeTab,
  onTabChange,
  emptyKey = "ui.queue.empty",
}: WorkQueueProps) {
  const baseId = useId();
  const tabId = (id: string) => `${baseId}-tab-${id}`;
  const selected = activeTab ?? tabs?.[0]?.id;

  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!tabs?.length || (event.key !== "ArrowRight" && event.key !== "ArrowLeft")) return;
    const step = event.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(index + step + tabs.length) % tabs.length];
    if (!next) return;
    onTabChange?.(next.id);
    document.getElementById(tabId(next.id))?.focus();
  };

  const list = items.length ? (
    <ul className="aip-queue__list" aria-label={translate(labelKey)}>
      {items.map((item) => (
        <li key={item.id} className="aip-queue__row">
          <button type="button" className="aip-queue__open" onClick={() => onOpen(item.id)}>
            <span className="aip-queue__id">{item.id}</span>
            {" "}
            <span className="aip-queue__text">
              <span className="aip-queue__title">{item.title}</span>
              {item.snippet && <span className="aip-queue__snippet">{item.snippet}</span>}
            </span>
          </button>
          {item.assetPath && <span className="aip-queue__asset">{item.assetPath}</span>}
          {item.due && <Due due={item.due} now={now} translate={translate} />}
          <StatusChip tone={item.status.tone} icon={item.status.icon} label={translate(item.status.labelKey)} />
          {item.actions?.length ? (
            <span className="aip-queue__actions">
              {item.actions.slice(0, QUEUE_MAX_ACTIONS).map((action) => (
                <Button
                  key={action.id}
                  variant="ghost"
                  aria-label={translate("ui.queue.action", { action: translate(action.labelKey), item: item.id })}
                  onClick={action.onSelect}
                >
                  {translate(action.labelKey)}
                </Button>
              ))}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  ) : (
    <p className="aip-queue__empty">{translate(emptyKey)}</p>
  );

  return (
    <div className="aip-queue">
      {tabs?.length ? (
        <>
          <div className="aip-queue__tabs" role="tablist" aria-label={translate(labelKey)}>
            {tabs.map((tab, index) => (
              <button
                key={tab.id}
                id={tabId(tab.id)}
                type="button"
                role="tab"
                className="aip-queue__tab"
                aria-selected={tab.id === selected}
                tabIndex={tab.id === selected ? 0 : -1}
                onClick={() => onTabChange?.(tab.id)}
                onKeyDown={(e) => onTabKey(e, index)}
              >
                {translate(tab.labelKey)}
                {tab.count !== undefined && <span className="aip-queue__count">{tab.count}</span>}
              </button>
            ))}
          </div>
          <div role="tabpanel" aria-labelledby={selected ? tabId(selected) : undefined}>
            {list}
          </div>
        </>
      ) : (
        list
      )}
    </div>
  );
}
