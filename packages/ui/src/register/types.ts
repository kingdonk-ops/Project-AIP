/**
 * The register contract (DESIGN-03). Every P1 register describes its columns and filters with
 * these types and hands `RegisterTable` a query adapter; the table never fetches by itself.
 */
import type { ReactNode } from "react";

export type SortDir = "asc" | "desc";

export interface RegisterColumn<T> {
  id: string;
  /** Terminology key of the header label. */
  headerKey: string;
  cell: (row: T) => ReactNode;
  /** The directions the server can sort this column by; `true` means both. Omitted: not sortable. */
  sortable?: boolean | readonly SortDir[];
  /** Shown unless the user hides it (default true). */
  defaultVisible?: boolean;
  /** Monospace cell (codes, ids). */
  mono?: boolean;
  /** The plain value written to CSV; defaults to the row's property named `id`. */
  csv?: (row: T) => unknown;
}

export interface RegisterFilterOption {
  value: string;
  labelKey: string;
}

export interface RegisterFilter {
  id: string;
  kind: "select" | "multi" | "text" | "date-range";
  labelKey: string;
  options?: readonly RegisterFilterOption[];
  /** Shown in the quick-filter row (status, assignee, asset, date). */
  quick?: boolean;
}

/** Filter values: one string, several (multi), or `[from, to]` ISO dates (date-range). */
export type FilterValue = string | readonly string[];

export interface RegisterQuery {
  filters: Readonly<Record<string, FilterValue>>;
  q?: string;
  sort?: { id: string; dir: SortDir };
  cursor?: string;
  limit: number;
  /** Visible column ids when the user changed them; omitted means the defaults. */
  columns?: readonly string[];
}

/** One server page: the shape of the API's cursor pages (`{items, nextCursor}`). */
export interface RegisterPage<T> {
  items: readonly T[];
  nextCursor: string | null;
}

/** What the caller's adapter over a generated TanStack Query hook returns. */
export interface RegisterQueryResult<T> {
  data: RegisterPage<T> | undefined;
  isPending: boolean;
  isError: boolean;
  refetch: () => unknown;
  /** The total row count when the server knows it (sets `aria-rowcount`). */
  total?: number;
  /** The failed response's `X-Request-Id`, shown with the error so support can find the request. */
  requestId?: string | null;
}

export interface BulkAction<T> {
  id: string;
  labelKey: string;
  /** Hidden unless the user holds this permission. */
  permission?: string;
  run: (rows: readonly T[]) => void;
}

/** Looks up a terminology key (the app passes its `t`). */
export type Translate = (key: string, params?: Record<string, string | number>) => string;

export const PAGE_SIZES = [25, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 50;
