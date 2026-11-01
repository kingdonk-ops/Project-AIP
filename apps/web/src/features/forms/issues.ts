/**
 * The server's template issues in one shape (FORMS-04): FORMS-01's lint issues (`{path, code,
 * message}`, from `POST /forms/lint` or a 422 `TEMPLATE_INVALID`) and FastAPI's request-validation
 * `detail` (`{loc, msg}`) both become `Issue`s the `IssueList` shows.
 */

export type IssuePath = readonly (string | number)[];

export interface Issue {
  path: IssuePath;
  code: string;
  message: string;
}

/** Every FORMS-01 (and FORMS-10) lint code; each has a `forms.lint.<CODE>` term. */
export const LINT_CODES = [
  "SCHEMA_INVALID",
  "TEMPLATE_TOO_LARGE",
  "DUPLICATE_KEY",
  "UNKNOWN_FIELD_TYPE",
  "OPTIONS_REQUIRED",
  "OPTIONS_NOT_ALLOWED",
  "DUPLICATE_OPTION",
  "UNIT_REQUIRED",
  "UNKNOWN_UNIT",
  "VALIDATION_NOT_ALLOWED",
  "VALIDATION_RANGE",
  "EXPRESSION_INVALID",
  "UNKNOWN_REFERENCE",
  "CONDITION_CYCLE",
  "RULE_READS_HIDDEN_FIELD",
] as const;

export function isLintCode(code: string): boolean {
  return (LINT_CODES as readonly string[]).includes(code);
}

/** `["sections", 0, "fields", 2, "key"]` → `sections[0].fields[2].key`. */
export function formatPath(path: IssuePath): string {
  let out = "";
  for (const part of path) {
    if (typeof part === "number") out += `[${part}]`;
    else out += out === "" ? part : `.${part}`;
  }
  return out;
}

function isPath(value: unknown): value is (string | number)[] {
  return Array.isArray(value) && value.every((p) => typeof p === "string" || typeof p === "number");
}

/** The lint issues of a `{issues}` body (lint result or 422 `TEMPLATE_INVALID`). */
export function lintIssues(body: unknown): Issue[] {
  if (typeof body !== "object" || body === null) return [];
  const raw = (body as { issues?: unknown }).issues;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item: unknown) => {
    if (typeof item !== "object" || item === null) return [];
    const { path, code, message } = item as { path?: unknown; code?: unknown; message?: unknown };
    if (typeof code !== "string") return [];
    return [{ path: isPath(path) ? path : [], code, message: typeof message === "string" ? message : "" }];
  });
}

/** FastAPI's 422 `detail` entries, with `body` dropped from each `loc`. */
export function requestIssues(body: unknown): Issue[] {
  if (typeof body !== "object" || body === null) return [];
  const detail = (body as { detail?: unknown }).detail;
  if (!Array.isArray(detail)) return [];
  return detail.flatMap((item: unknown) => {
    if (typeof item !== "object" || item === null) return [];
    const { loc, msg, type } = item as { loc?: unknown; msg?: unknown; type?: unknown };
    const path = isPath(loc) ? (loc[0] === "body" ? loc.slice(1) : loc) : [];
    return [{ path, code: typeof type === "string" ? type : "invalid", message: typeof msg === "string" ? msg : "" }];
  });
}
