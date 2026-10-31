/**
 * URL search state of the external users register (PORTAL-07), in DESIGN-03's register format:
 * `status`, `expiring` (days), `project` (a project id), `q`, `cursor`, `limit` and `cols`. There is
 * no `sort`: the API lists portal users oldest first only. `validatePortalUsersSearch` is the route's
 * `validateSearch` (unknown params ignored, invalid values dropped, never thrown).
 */
import type { PortalUsersListParams, PortalUsersListStatus } from "@aip/api-client";
import { decodeRegisterQuery, encodeRegisterQuery, type RegisterQuery, type RegisterSpec } from "@aip/ui";

export const PORTAL_USER_STATUSES = ["invited", "active", "suspended"] as const satisfies readonly PortalUsersListStatus[];
/** The "expiring soon" windows offered, in days (PORTAL-08 reminds from 30 days out). */
export const EXPIRING_WINDOWS = ["7", "30", "90"] as const;
/** A live grant ending within this many days is flagged "expiring soon" in the register. */
export const EXPIRING_SOON_DAYS = 30;

export const DEFAULT_LIMIT = 50;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value);
}

export const PORTAL_USERS_SPEC = {
  filters: [
    { id: "status", kind: "select", options: PORTAL_USER_STATUSES.map((value) => ({ value })) },
    { id: "expiring", kind: "select", options: EXPIRING_WINDOWS.map((value) => ({ value })) },
    // The tenant's projects are data, so any value is kept here and checked in `toListParams`.
    { id: "project", kind: "select" },
  ],
  sortable: {},
  columns: ["email", "company", "status", "projects", "expiry", "signedIn"],
  defaultLimit: DEFAULT_LIMIT,
} as const satisfies RegisterSpec;

export function portalUsersQuery(search: Record<string, unknown>): RegisterQuery {
  const query = decodeRegisterQuery(search, PORTAL_USERS_SPEC);
  if (query.filters.project === undefined || isUuid(query.filters.project)) return query;
  const { project: _dropped, ...filters } = query.filters;
  return { ...query, filters };
}

export function toSearch(query: RegisterQuery): Record<string, string> {
  return encodeRegisterQuery(query, DEFAULT_LIMIT);
}

export function validatePortalUsersSearch(search: Record<string, unknown>): Record<string, string> {
  return toSearch(portalUsersQuery(search));
}

function isStatus(value: unknown): value is PortalUsersListStatus {
  return typeof value === "string" && (PORTAL_USER_STATUSES as readonly string[]).includes(value);
}

/** The list parameters of a register query. */
export function toListParams(query: RegisterQuery): PortalUsersListParams {
  const { status, expiring, project } = query.filters;
  const days = Number(expiring);
  return {
    ...(isStatus(status) ? { status } : {}),
    ...(Number.isInteger(days) && days > 0 ? { expiringWithinDays: days } : {}),
    ...(isUuid(project) ? { projectId: project } : {}),
    ...(query.q ? { q: query.q } : {}),
    limit: query.limit,
    ...(query.cursor ? { cursor: query.cursor } : {}),
  };
}
