import type { Translate } from "@aip/ui";
import { useId, type MouseEvent } from "react";

export interface ErrorSummaryItem {
  fieldKey: string;
  /** The field's label (already translated). */
  label: string;
  /** The error text (already translated). */
  message: string;
  /** DOM id of the field's wrapper. */
  targetId: string;
}

/** What the summary focuses inside a field wrapper: its first real, focusable control. */
const CONTROL_SELECTOR = [
  'input:not([type="hidden"]):not([aria-hidden="true"])',
  'select:not([aria-hidden="true"])',
  "textarea",
  "button",
  '[role="combobox"]',
  '[role="checkbox"]',
].join(",");

/** Focuses the first control of the field with this wrapper id. */
export function focusField(targetId: string): boolean {
  const wrapper = document.getElementById(targetId);
  const control = wrapper?.querySelector<HTMLElement>(CONTROL_SELECTOR);
  if (!control) return false;
  control.focus();
  return true;
}

/**
 * The error summary shown after a submit attempt (`showErrors="all"`): a `role="alert"` region with
 * one link per error; activating a link focuses that field's control.
 */
export function ErrorSummary({ items, t }: { items: readonly ErrorSummaryItem[]; t: Translate }) {
  const titleId = useId();
  if (items.length === 0) return null;
  const onActivate = (event: MouseEvent<HTMLAnchorElement>, targetId: string) => {
    if (focusField(targetId)) event.preventDefault();
  };
  return (
    <div className="aip-form-renderer__summary" role="alert" aria-labelledby={titleId}>
      <h2 id={titleId} className="aip-form-renderer__summary-title">
        {t("forms.renderer.error_summary_title")}
      </h2>
      <ul>
        {items.map((item) => (
          <li key={item.fieldKey}>
            <a href={`#${item.targetId}`} onClick={(e) => onActivate(e, item.targetId)}>
              {t("forms.renderer.error_summary_item", { field: item.label, message: item.message })}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
