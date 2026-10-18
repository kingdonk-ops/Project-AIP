/**
 * URL search state of the projects register (PROJECTS-02, PROJECTS-06).
 *
 * The URL holds DESIGN-03's register format (`status`, `q`, `sort=-code`, `cursor`, `limit`, `cols`),
 * so links written for PROJECTS-02 (`?status=active&q=kips`) still open. `validateProjectsSearch` is
 * the route's `validateSearch`: it decodes with `decodeRegisterQuery` (unknown params ignored,
 * invalid values dropped, never thrown) and re-encodes, so the route's search is always the
 * canonical flat form; the page decodes it again with `projectsQuery`.
 */
import type { ProjectsExportParams, ProjectsListParams, ProjectsListSort, ProjectsListStatusItem } from "@aip/api-client";
import { decodeRegisterQuery, encodeRegisterQuery, type RegisterQuery, type RegisterSpec } from "@aip/ui";

export const PROJECT_STATUSES = ["draft", "active", "closing", "archived"] as const satisfies readonly ProjectsListStatusItem[];
export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

export const DEFAULT_LIMIT = 50;
const MAX_CODE = 32;

/** Register column ids the API can sort by, and the API's name for each. */
const SORT_FIELDS = { code: "code", name: "name", updated: "updated_at" } as const;

export const PROJECTS_SPEC = {
  filters: [{ id: "status", kind: "select", options: PROJECT_STATUSES.map((value) => ({ value })) }],
  sortable: { code: ["asc", "desc"], name: ["asc", "desc"], updated: ["asc", "desc"] },
  columns: ["code", "name", "site", "region", "status", "updated"],
  defaultLimit: DEFAULT_LIMIT,
} as const satisfies RegisterSpec;

/** The route's search: the encoded register query plus the code of a project just created. */
export type ProjectsSearch = Record<string, string> & {
  /** The code of the project just created, for the confirmation message. */
  created?: string;
};

export function projectsQuery(search: Record<string, unknown>): RegisterQuery {
  return decodeRegisterQuery(search, PROJECTS_SPEC);
}

export function toSearch(query: RegisterQuery): ProjectsSearch {
  return encodeRegisterQuery(query, DEFAULT_LIMIT);
}

export function validateProjectsSearch(search: Record<string, unknown>): ProjectsSearch {
  const out = toSearch(projectsQuery(search));
  const created = typeof search.created === "string" ? search.created.trim() : "";
  if (created && created.length <= MAX_CODE) out.created = created;
  return out;
}

function isStatus(value: unknown): value is ProjectStatus {
  return typeof value === "string" && (PROJECT_STATUSES as readonly string[]).includes(value);
}

/** The filters and sort of a register query as API parameters (the export takes exactly these). */
export function toExportParams(query: RegisterQuery): ProjectsExportParams {
  const status = query.filters.status;
  const statuses = (typeof status === "string" ? [status] : (status ?? [])).filter(isStatus);
  const field = query.sort ? SORT_FIELDS[query.sort.id as keyof typeof SORT_FIELDS] : undefined;
  const sort = field ? (`${query.sort?.dir === "desc" ? "-" : ""}${field}` as ProjectsListSort) : undefined;
  return {
    ...(sort ? { sort } : {}),
    ...(statuses.length ? { status: statuses } : {}),
    ...(query.q ? { q: query.q } : {}),
  };
}

/** The list parameters: the export's, plus the page size and position. */
export function toListParams(query: RegisterQuery): ProjectsListParams {
  return { ...toExportParams(query), limit: query.limit, ...(query.cursor ? { cursor: query.cursor } : {}) };
}
