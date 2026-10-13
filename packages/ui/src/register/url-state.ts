/**
 * Pure encoder and decoder between `RegisterQuery` and URL search params (DESIGN-03). No router
 * import: a route's `validateSearch` calls `decodeRegisterQuery`, and changes navigate with
 * `encodeRegisterQuery(query)` (replace). Unknown params are ignored and invalid values dropped,
 * never thrown, so a hand-edited or stale URL always opens.
 *
 * Format: each filter is a param named by its id (several values comma-separated; a date range is
 * `from..to`), `q` the free text, `sort=code` or `sort=-code` (descending), `cursor`, `limit`
 * (omitted at the default) and `cols` (visible column ids, comma-separated; omitted at defaults).
 */
import { DEFAULT_PAGE_SIZE, PAGE_SIZES, type FilterValue, type RegisterQuery, type SortDir } from "./types";

export interface RegisterSpec {
  filters: readonly { id: string; kind: "select" | "multi" | "text" | "date-range"; options?: readonly { value: string }[] }[];
  /** Sortable column ids and the directions each allows. */
  sortable: Readonly<Record<string, readonly SortDir[]>>;
  columns?: readonly string[];
  defaultLimit?: number;
  pageSizes?: readonly number[];
}

const MAX_TEXT = 100;
const MAX_CURSOR = 1024;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const RESERVED = new Set(["q", "sort", "cursor", "limit", "cols"]);

type Params = Record<string, unknown>;

function toParams(input: Params | URLSearchParams | string): Params {
  if (typeof input === "string" || input instanceof URLSearchParams) {
    const params = typeof input === "string" ? new URLSearchParams(input.replace(/^\?/, "")) : input;
    const out: Params = {};
    for (const [key, value] of params) out[key] = value;
    return out;
  }
  return input;
}

function text(value: unknown, max: number): string | undefined {
  if (typeof value === "number") value = String(value);
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 && trimmed.length <= max ? trimmed : undefined;
}

function list(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === "string");
  const s = text(value, 2000);
  return s ? s.split(",").map((v) => v.trim()).filter(Boolean) : [];
}

function own(record: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

export function decodeRegisterQuery(input: Params | URLSearchParams | string, spec: RegisterSpec): RegisterQuery {
  const params = toParams(input);
  const defaultLimit = spec.defaultLimit ?? DEFAULT_PAGE_SIZE;
  const sizes = spec.pageSizes ?? PAGE_SIZES;
  const query: { -readonly [K in keyof RegisterQuery]: RegisterQuery[K] } = { filters: {}, limit: defaultLimit };
  const filters: Record<string, FilterValue> = {};

  for (const filter of spec.filters) {
    if (RESERVED.has(filter.id) || !own(params, filter.id)) continue;
    const raw = params[filter.id];
    const allowed = filter.options ? new Set(filter.options.map((o) => o.value)) : null;
    if (filter.kind === "multi") {
      const values = list(raw).filter((v) => !allowed || allowed.has(v));
      if (values.length) filters[filter.id] = [...new Set(values)];
    } else if (filter.kind === "date-range") {
      const [from = "", to = ""] = (text(raw, 32) ?? "").split("..");
      if ((from === "" || ISO_DATE.test(from)) && (to === "" || ISO_DATE.test(to)) && (from || to)) {
        filters[filter.id] = [from, to];
      }
    } else {
      const value = text(raw, MAX_TEXT);
      if (value && (!allowed || allowed.has(value))) filters[filter.id] = value;
    }
  }
  query.filters = filters;

  const q = text(params.q, MAX_TEXT);
  if (q) query.q = q;

  const sort = text(params.sort, 64);
  if (sort) {
    const dir: SortDir = sort.startsWith("-") ? "desc" : "asc";
    const id = sort.replace(/^-/, "");
    if (own(spec.sortable, id) && spec.sortable[id]?.includes(dir)) query.sort = { id, dir };
  }

  const cursor = text(params.cursor, MAX_CURSOR);
  if (cursor) query.cursor = cursor;

  const limit = Number(text(params.limit, 4));
  if (Number.isInteger(limit) && sizes.includes(limit)) query.limit = limit;

  if (spec.columns) {
    const known = new Set(spec.columns);
    const cols = list(params.cols).filter((c) => known.has(c));
    if (cols.length) query.columns = [...new Set(cols)];
  }
  return query;
}

export function encodeRegisterQuery(query: RegisterQuery, defaultLimit: number = DEFAULT_PAGE_SIZE): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [id, value] of Object.entries(query.filters)) {
    if (RESERVED.has(id)) continue;
    if (typeof value === "string") {
      if (value) out[id] = value;
    } else if (value.length === 2 && value.some((v) => ISO_DATE.test(v)) && value.every((v) => v === "" || ISO_DATE.test(v))) {
      out[id] = `${value[0]}..${value[1]}`;
    } else if (value.length) {
      out[id] = value.join(",");
    }
  }
  if (query.q) out.q = query.q;
  if (query.sort) out.sort = `${query.sort.dir === "desc" ? "-" : ""}${query.sort.id}`;
  if (query.cursor) out.cursor = query.cursor;
  if (query.limit !== defaultLimit) out.limit = String(query.limit);
  if (query.columns?.length) out.cols = query.columns.join(",");
  return out;
}
