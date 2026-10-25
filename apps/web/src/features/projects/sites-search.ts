/**
 * URL search state of the sites register (PROJECTS-07). Sites have no server-side sort or status
 * filter (projects/routes.py: list is limit/cursor/q only), so the register keeps just the search
 * text, column choices and cursor in the URL, in DESIGN-03's flat format.
 */
import type { SitesListParams } from "@aip/api-client";
import { decodeRegisterQuery, encodeRegisterQuery, type RegisterQuery, type RegisterSpec } from "@aip/ui";

export const DEFAULT_LIMIT = 50;

export const SITES_SPEC = {
  filters: [],
  sortable: {},
  columns: ["code", "name", "timezone", "system", "updated"],
  defaultLimit: DEFAULT_LIMIT,
} as const satisfies RegisterSpec;

export type SitesSearch = Record<string, string>;

export function sitesQuery(search: Record<string, unknown>): RegisterQuery {
  return decodeRegisterQuery(search, SITES_SPEC);
}

export function toSitesSearch(query: RegisterQuery): SitesSearch {
  return encodeRegisterQuery(query, DEFAULT_LIMIT);
}

export function validateSitesSearch(search: Record<string, unknown>): SitesSearch {
  return toSitesSearch(sitesQuery(search));
}

/** The list parameters for one page of the register query. */
export function toSitesListParams(query: RegisterQuery): SitesListParams {
  return {
    limit: query.limit,
    ...(query.q ? { q: query.q } : {}),
    ...(query.cursor ? { cursor: query.cursor } : {}),
  };
}
