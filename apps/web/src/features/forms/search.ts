/**
 * URL search state of the form template pages (FORMS-04).
 *
 * The register uses DESIGN-03's flat format (`kind`, `status`, `q`, `cols`). FORMS-01's list has no
 * cursor and no sort (ordered by code, at most 200), so the register asks for one page of 200 and
 * offers no sortable column; FORMS-09 adds paging and sort. The detail page keeps its tab and the
 * revisions it shows or compares (`tab`, `rev`, `from`, `to`); invalid values are dropped, never thrown.
 */
import type { FormsTemplatesListParams } from "@aip/api-client";
import { decodeRegisterQuery, encodeRegisterQuery, type RegisterQuery, type RegisterSpec } from "@aip/ui";
import { TEMPLATE_KINDS } from "./templateJson";

export const TEMPLATE_STATUSES = ["draft", "active", "retired"] as const;
export type TemplateStatus = (typeof TEMPLATE_STATUSES)[number];

/** The API's maximum `limit`: the whole list in one page. */
export const PAGE_SIZE = 200;
export const PAGE_SIZES = [PAGE_SIZE] as const;

export const TEMPLATES_SPEC = {
  filters: [
    { id: "kind", kind: "select", options: TEMPLATE_KINDS.map((value) => ({ value })) },
    { id: "status", kind: "select", options: TEMPLATE_STATUSES.map((value) => ({ value })) },
  ],
  sortable: {},
  columns: ["code", "name", "kind", "status", "revision", "updated"],
  defaultLimit: PAGE_SIZE,
  pageSizes: PAGE_SIZES,
} as const satisfies RegisterSpec;

export type TemplatesSearch = Record<string, string>;

export function templatesQuery(search: Record<string, unknown>): RegisterQuery {
  return decodeRegisterQuery(search, TEMPLATES_SPEC);
}

export function toTemplatesSearch(query: RegisterQuery): TemplatesSearch {
  return encodeRegisterQuery(query, PAGE_SIZE);
}

export function validateTemplatesSearch(search: Record<string, unknown>): TemplatesSearch {
  return toTemplatesSearch(templatesQuery(search));
}

function single(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

export function toListParams(query: RegisterQuery): FormsTemplatesListParams {
  const kind = single(query.filters.kind);
  const status = single(query.filters.status);
  return {
    ...(kind ? { kind } : {}),
    ...(status ? { status } : {}),
    ...(query.q ? { q: query.q } : {}),
    limit: PAGE_SIZE,
  };
}

export const DETAIL_TABS = ["revisions", "compare"] as const;
export type DetailTab = (typeof DETAIL_TABS)[number];

export interface TemplateSearch {
  tab?: DetailTab;
  /** The revision number shown on the Revisions tab. */
  rev?: number;
  /** The revision numbers compared on the Compare tab. */
  from?: number;
  to?: number;
}

function revisionNo(value: unknown): number | undefined {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isInteger(n) && n >= 1 && n <= 100_000 ? n : undefined;
}

export function validateTemplateSearch(search: Record<string, unknown>): TemplateSearch {
  const out: TemplateSearch = {};
  if (typeof search.tab === "string" && (DETAIL_TABS as readonly string[]).includes(search.tab)) {
    out.tab = search.tab as DetailTab;
  }
  for (const name of ["rev", "from", "to"] as const) {
    const n = revisionNo(search[name]);
    if (n !== undefined) out[name] = n;
  }
  return out;
}
