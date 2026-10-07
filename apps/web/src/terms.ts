/**
 * Terminology placeholder. User-facing strings are looked up by key with en-AU defaults.
 * The real terminology service (TERMS tasks) replaces this map.
 */
const enAU = {
  "app.title": "AIP",
} as const;

export type TermKey = keyof typeof enAU;

export function t(key: TermKey): string {
  return enAU[key];
}
