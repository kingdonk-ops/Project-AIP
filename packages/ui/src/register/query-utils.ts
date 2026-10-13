import type { RegisterQuery } from "./types";

/** A copy of `query` without the given optional keys (e.g. drop the cursor on a filter change). */
export function omit(query: RegisterQuery, ...keys: ("cursor" | "q" | "columns" | "sort")[]): RegisterQuery {
  const copy: Partial<Record<keyof RegisterQuery, unknown>> = { ...query };
  for (const key of keys) delete copy[key];
  return copy as RegisterQuery;
}
