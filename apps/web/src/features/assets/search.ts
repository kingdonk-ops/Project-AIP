/**
 * URL search state of the assets page (ASSETS-03).
 *
 * The URL holds DESIGN-03's register format (`itemType`, `q`, `sort=-name`, `cursor`, `limit`,
 * `cols`) plus `under` (the asset whose subtree the register shows, set by the tree) and `created`
 * (the internal tag of an asset just created, for the confirmation). `validateAssetsSearch` is the
 * route's `validateSearch`: unknown params are ignored and invalid values dropped, never thrown, so
 * the URL alone reproduces the view.
 */
import type { AssetsExportParams, AssetsListParams, AssetsListSort } from "@aip/api-client";
import { decodeRegisterQuery, encodeRegisterQuery, type RegisterQuery, type RegisterSpec } from "@aip/ui";

export const DEFAULT_LIMIT = 50;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const INTERNAL_TAG = /^AT-[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}$/;

/** Register column ids the API can sort by, and the API's name for each. */
const SORT_FIELDS = { name: "name", tagNumber: "tagNumber", updated: "updatedAt" } as const;

export const ASSETS_SPEC = {
  filters: [{ id: "itemType", kind: "multi" }],
  sortable: { name: ["asc", "desc"], tagNumber: ["asc", "desc"], updated: ["asc", "desc"] },
  columns: ["name", "tagNumber", "internalTag", "itemType", "parent", "updated", "actions"],
  defaultLimit: DEFAULT_LIMIT,
} as const satisfies RegisterSpec;

/** The route's search: the encoded register query plus the tree scope and the created tag. */
export type AssetsSearch = Record<string, string> & {
  /** The asset whose subtree the register lists. */
  under?: string;
  /** The internal tag of the asset just created, for the confirmation message. */
  created?: string;
};

export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value);
}

export function assetsQuery(search: Record<string, unknown>): RegisterQuery {
  return decodeRegisterQuery(search, ASSETS_SPEC);
}

/** The search for `query` within `under` (omitted when unset). */
export function toSearch(query: RegisterQuery, under?: string): AssetsSearch {
  const out: AssetsSearch = encodeRegisterQuery(query, DEFAULT_LIMIT);
  if (under) out.under = under;
  return out;
}

export function validateAssetsSearch(search: Record<string, unknown>): AssetsSearch {
  const under = isUuid(search.under) ? search.under : undefined;
  const out = toSearch(assetsQuery(search), under);
  const created = typeof search.created === "string" ? search.created.trim() : "";
  if (INTERNAL_TAG.test(created)) out.created = created;
  return out;
}

/** The filters and sort of a register query within `under`, as API parameters (the export's). */
export function toExportParams(query: RegisterQuery, under?: string): AssetsExportParams {
  const raw = query.filters.itemType;
  const itemTypes = (typeof raw === "string" ? [raw] : (raw ?? [])).filter(isUuid);
  const field = query.sort ? SORT_FIELDS[query.sort.id as keyof typeof SORT_FIELDS] : undefined;
  const sort = field ? (`${query.sort?.dir === "desc" ? "-" : ""}${field}` as AssetsListSort) : undefined;
  return {
    ...(sort ? { sort } : {}),
    ...(under ? { under } : {}),
    ...(itemTypes.length ? { itemTypeId: itemTypes } : {}),
    ...(query.q ? { q: query.q } : {}),
  };
}

/** The list parameters: the export's, plus the page size and position. */
export function toListParams(query: RegisterQuery, under?: string): AssetsListParams {
  return { ...toExportParams(query, under), limit: query.limit, ...(query.cursor ? { cursor: query.cursor } : {}) };
}
