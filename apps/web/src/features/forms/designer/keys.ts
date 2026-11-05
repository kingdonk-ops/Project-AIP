/**
 * Contract keys from labels (FORMS-11). A key matches `^[a-z][a-z0-9_]{0,62}$`: lower case, every
 * run of other characters becomes `_`, a leading digit gets an `f_` prefix, and a key already taken
 * gets `_2`, `_3`, … Sections, fields and section rules share one key namespace, so `taken` is all
 * of them (`allKeys` in `model.ts`).
 */

export const KEY_PATTERN = /^[a-z][a-z0-9_]{0,62}$/;
export const KEY_MAX = 63;

export function isValidKey(key: string): boolean {
  return KEY_PATTERN.test(key);
}

function clip(base: string, length: number): string {
  return base.slice(0, length).replace(/_+$/, "");
}

/** The key a label suggests, unique among `taken`. */
export function keyFromLabel(label: string, taken: Iterable<string>): string {
  let base = label
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (base === "") base = "field";
  if (/^[0-9]/.test(base)) base = `f_${base}`;
  base = clip(base, KEY_MAX);

  const used = new Set(taken);
  if (!used.has(base)) return base;
  for (let n = 2; ; n++) {
    const suffix = `_${n}`;
    const candidate = `${clip(base, KEY_MAX - suffix.length)}${suffix}`;
    if (!used.has(candidate)) return candidate;
  }
}
