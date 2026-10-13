/**
 * Column chooser (DESIGN-03): show or hide columns and restore the defaults. The preference is
 * kept per register id behind `ColumnPrefsStore`; `localStorageColumnPrefs` is the store for now,
 * and a server-backed store can replace it without touching the table.
 */
import { useId } from "react";
import { Button } from "../components/button";
import type { RegisterColumn, Translate } from "./types";

export interface ColumnPrefsStore {
  get(registerId: string): string[] | null;
  /** `null` forgets the preference (back to the defaults). */
  set(registerId: string, columns: readonly string[] | null): void;
}

const PREFIX = "aip.register.columns.";

/** Browser storage; every access is guarded (private mode, blocked storage). */
export const localStorageColumnPrefs: ColumnPrefsStore = {
  get(registerId) {
    try {
      const raw = globalThis.localStorage?.getItem(PREFIX + registerId);
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      return Array.isArray(parsed) && parsed.every((v) => typeof v === "string") ? (parsed as string[]) : null;
    } catch {
      return null;
    }
  },
  set(registerId, columns) {
    try {
      if (columns === null) globalThis.localStorage?.removeItem(PREFIX + registerId);
      else globalThis.localStorage?.setItem(PREFIX + registerId, JSON.stringify(columns));
    } catch {
      // Storage is a convenience: losing the preference is fine.
    }
  },
};

export function defaultColumns<T>(columns: readonly RegisterColumn<T>[]): string[] {
  return columns.filter((c) => c.defaultVisible !== false).map((c) => c.id);
}

export interface ColumnChooserProps<T> {
  columns: readonly RegisterColumn<T>[];
  visible: readonly string[];
  /** The new visible ids, or `null` to restore the defaults. */
  onChange: (visible: readonly string[] | null) => void;
  translate: Translate;
}

export function ColumnChooser<T>({ columns, visible, onChange, translate }: ColumnChooserProps<T>) {
  const id = useId();
  const shown = new Set(visible);
  return (
    <details className="aip-register__columns">
      <summary>{translate("register.columns")}</summary>
      <fieldset>
        <legend>{translate("register.columns")}</legend>
        {columns.map((column) => (
          <label key={column.id} htmlFor={`${id}-${column.id}`} className="aip-register__column-option">
            <input
              id={`${id}-${column.id}`}
              type="checkbox"
              checked={shown.has(column.id)}
              // The last visible column cannot be hidden.
              disabled={shown.has(column.id) && shown.size === 1}
              onChange={(e) => {
                const next = columns
                  .map((c) => c.id)
                  .filter((c) => (c === column.id ? e.target.checked : shown.has(c)));
                onChange(next);
              }}
            />
            {translate(column.headerKey)}
          </label>
        ))}
        <Button variant="ghost" onClick={() => onChange(null)}>
          {translate("register.restoreDefaults")}
        </Button>
      </fieldset>
    </details>
  );
}
