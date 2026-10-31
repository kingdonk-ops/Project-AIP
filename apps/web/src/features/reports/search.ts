/**
 * URL search state of the report register (REPORTS-04), in DESIGN-03's register format: `status`,
 * `q`, `cursor`, `limit` and `cols`. There is no `sort`: the API lists reports newest first only.
 * `validateReportsSearch` is the route's `validateSearch` (unknown params ignored, invalid values
 * dropped, never thrown); the page decodes it again with `reportsQuery`.
 */
import type { ReportsRendersListParams, ReportsRendersListStatusItem } from "@aip/api-client";
import { decodeRegisterQuery, encodeRegisterQuery, type RegisterQuery, type RegisterSpec } from "@aip/ui";

export const REPORT_STATUSES = ["queued", "running", "succeeded", "failed"] as const satisfies readonly ReportsRendersListStatusItem[];
export type ReportStatus = (typeof REPORT_STATUSES)[number];

export const DEFAULT_LIMIT = 50;

export const REPORTS_SPEC = {
  filters: [{ id: "status", kind: "select", options: REPORT_STATUSES.map((value) => ({ value })) }],
  sortable: {},
  columns: ["status", "template", "record", "generated", "error", "download"],
  defaultLimit: DEFAULT_LIMIT,
} as const satisfies RegisterSpec;

export function reportsQuery(search: Record<string, unknown>): RegisterQuery {
  return decodeRegisterQuery(search, REPORTS_SPEC);
}

export function toSearch(query: RegisterQuery): Record<string, string> {
  return encodeRegisterQuery(query, DEFAULT_LIMIT);
}

export function validateReportsSearch(search: Record<string, unknown>): Record<string, string> {
  return toSearch(reportsQuery(search));
}

function isStatus(value: unknown): value is ReportStatus {
  return typeof value === "string" && (REPORT_STATUSES as readonly string[]).includes(value);
}

/** The list parameters of a register query. */
export function toListParams(query: RegisterQuery): ReportsRendersListParams {
  const status = query.filters.status;
  const statuses = (typeof status === "string" ? [status] : (status ?? [])).filter(isStatus);
  return {
    ...(statuses.length ? { status: statuses } : {}),
    ...(query.q ? { q: query.q } : {}),
    limit: query.limit,
    ...(query.cursor ? { cursor: query.cursor } : {}),
  };
}
