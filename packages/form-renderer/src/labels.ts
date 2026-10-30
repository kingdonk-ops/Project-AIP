import type { Translate } from "@aip/ui";

/** Anything the template labels: a section, a field or an option. */
export interface Labelled {
  label: string;
  labelKey?: string;
}

/**
 * The text shown for a template label (FORMS-01): `labelKey ? t(labelKey) : label`. `label` is the
 * tenant's own content; UI chrome never comes from the template.
 */
export function labelOf(t: Translate, item: Labelled): string {
  return item.labelKey ? t(item.labelKey) : item.label;
}

/** Evaluator params (`Record<string, unknown>`) narrowed to what `t` takes; none → `undefined`. */
export function termParams(params: Record<string, unknown>): Record<string, string | number> | undefined {
  if (Object.keys(params).length === 0) return undefined;
  const out: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(params)) {
    out[key] = typeof value === "number" ? value : String(value);
  }
  return out;
}
