/**
 * The register filter bar (DESIGN-03): declared filters plus a free-text search (debounced 300 ms)
 * and "Clear all". Quick filters (`quick: true`, e.g. status, assignee, asset, date) sit in their
 * own row. Native controls keep it keyboard-operable everywhere; every label is a term key.
 */
import { useEffect, useId, useRef, useState } from "react";
import { omit } from "./query-utils";
import { Button } from "../components/button";
import { Input } from "../components/input";
import { Label } from "../components/label";
import type { FilterValue, RegisterFilter, RegisterQuery, Translate } from "./types";

export const SEARCH_DEBOUNCE_MS = 300;

export interface FilterBarProps {
  filters: readonly RegisterFilter[];
  query: RegisterQuery;
  /** A new query; any filter change starts again from the first page (the cursor is dropped). */
  onChange: (next: RegisterQuery) => void;
  translate: Translate;
  /** Show the free-text search (default true). */
  search?: boolean;
}

function withFilter(query: RegisterQuery, id: string, value: FilterValue | undefined): RegisterQuery {
  const filters = { ...query.filters };
  if (value === undefined || value.length === 0 || (Array.isArray(value) && value.every((v) => !v))) {
    delete filters[id];
  } else {
    filters[id] = value;
  }
  return { ...omit(query, "cursor"), filters };
}

function FilterControl({
  filter,
  value,
  onValue,
  translate,
}: {
  filter: RegisterFilter;
  value: FilterValue | undefined;
  onValue: (value: FilterValue | undefined) => void;
  translate: Translate;
}) {
  const id = useId();
  const label = translate(filter.labelKey);
  if (filter.kind === "date-range") {
    const [from = "", to = ""] = Array.isArray(value) ? value : [];
    return (
      <fieldset className="aip-register__filter aip-register__filter--range">
        <legend>{label}</legend>
        <Label htmlFor={`${id}-from`}>{translate("register.dateFrom")}</Label>
        <Input id={`${id}-from`} type="date" value={from} onChange={(e) => onValue([e.target.value, to])} />
        <Label htmlFor={`${id}-to`}>{translate("register.dateTo")}</Label>
        <Input id={`${id}-to`} type="date" value={to} onChange={(e) => onValue([from, e.target.value])} />
      </fieldset>
    );
  }
  if (filter.kind === "text") {
    return (
      <div className="aip-register__filter">
        <Label htmlFor={id}>{label}</Label>
        <Input id={id} value={typeof value === "string" ? value : ""} onChange={(e) => onValue(e.target.value || undefined)} />
      </div>
    );
  }
  const multiple = filter.kind === "multi";
  const selected = Array.isArray(value) ? value : typeof value === "string" ? [value] : [];
  return (
    <div className="aip-register__filter">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        className="aip-register__select"
        multiple={multiple}
        value={multiple ? [...selected] : (selected[0] ?? "")}
        onChange={(e) => {
          const values = Array.from(e.target.selectedOptions, (o) => o.value).filter(Boolean);
          onValue(multiple ? values : values[0]);
        }}
      >
        {!multiple && <option value="">{translate("register.any")}</option>}
        {(filter.options ?? []).map((o) => (
          <option key={o.value} value={o.value}>
            {translate(o.labelKey)}
          </option>
        ))}
      </select>
    </div>
  );
}

export function FilterBar({ filters, query, onChange, translate, search = true }: FilterBarProps) {
  const searchId = useId();
  const [text, setText] = useState(query.q ?? "");
  const [syncedQ, setSyncedQ] = useState(query.q);
  // Follow the URL when it changes elsewhere (back button, Clear all): a render-time update.
  if (query.q !== syncedQ) {
    setSyncedQ(query.q);
    setText(query.q ?? "");
  }
  const latest = useRef(query);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    latest.current = query;
  });
  useEffect(() => () => clearTimeout(timer.current), []);

  function onSearch(value: string) {
    setText(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const q = value.trim();
      if ((latest.current.q ?? "") === q) return;
      const rest = omit(latest.current, "cursor", "q");
      onChange(q ? { ...rest, q } : rest);
    }, SEARCH_DEBOUNCE_MS);
  }

  const quick = filters.filter((f) => f.quick);
  const others = filters.filter((f) => !f.quick);
  const active = Object.keys(query.filters).length > 0 || Boolean(query.q);
  const control = (filter: RegisterFilter) => (
    <FilterControl
      key={filter.id}
      filter={filter}
      value={query.filters[filter.id]}
      translate={translate}
      onValue={(value) => onChange(withFilter(query, filter.id, value))}
    />
  );

  return (
    <div className="aip-register__filters" role="search">
      {quick.length > 0 && <div className="aip-register__quick">{quick.map(control)}</div>}
      <div className="aip-register__filter-row">
        {search && (
          <div className="aip-register__filter">
            <Label htmlFor={searchId}>{translate("register.search")}</Label>
            <Input id={searchId} type="search" value={text} onChange={(e) => onSearch(e.target.value)} />
          </div>
        )}
        {others.map(control)}
        <Button
          variant="ghost"
          disabled={!active}
          onClick={() => {
            clearTimeout(timer.current);
            setText("");
            onChange({ ...omit(query, "cursor", "q"), filters: {} });
          }}
        >
          {translate("register.clearAll")}
        </Button>
      </div>
    </div>
  );
}
