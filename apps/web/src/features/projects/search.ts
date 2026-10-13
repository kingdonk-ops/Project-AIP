/**
 * URL search state of the projects register (PROJECTS-02).
 *
 * `validateProjectsSearch` is the route's `validateSearch`: it keeps only well-formed values and
 * silently drops the rest, so a hand-edited or stale URL never breaks the page. `limit` is omitted
 * when it is the default, so the canonical URL stays short.
 */
import type { ProjectsListStatusItem } from "@aip/api-client";

export const PROJECT_STATUSES = ["draft", "active", "closing", "archived"] as const satisfies readonly ProjectsListStatusItem[];
export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

export const DEFAULT_LIMIT = 50;
export const MAX_LIMIT = 200;
const MAX_QUERY = 100;
const MAX_CURSOR = 1024;
const MAX_CODE = 32;

export interface ProjectsSearch {
  status?: ProjectStatus;
  q?: string;
  cursor?: string;
  limit?: number;
  /** The code of the project just created, for the confirmation message. */
  created?: string;
}

function isStatus(value: unknown): value is ProjectStatus {
  return typeof value === "string" && (PROJECT_STATUSES as readonly string[]).includes(value);
}

function boundedString(value: unknown, max: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 && trimmed.length <= max ? trimmed : undefined;
}

function limitOf(value: unknown): number | undefined {
  const n = typeof value === "number" ? value : typeof value === "string" && /^\d+$/.test(value) ? Number(value) : NaN;
  return Number.isInteger(n) && n >= 1 && n <= MAX_LIMIT && n !== DEFAULT_LIMIT ? n : undefined;
}

export function validateProjectsSearch(search: Record<string, unknown>): ProjectsSearch {
  const out: ProjectsSearch = {};
  if (isStatus(search.status)) out.status = search.status;
  const q = boundedString(search.q, MAX_QUERY);
  if (q) out.q = q;
  const cursor = boundedString(search.cursor, MAX_CURSOR);
  if (cursor) out.cursor = cursor;
  const limit = limitOf(search.limit);
  if (limit) out.limit = limit;
  const created = boundedString(search.created, MAX_CODE);
  if (created) out.created = created;
  return out;
}
