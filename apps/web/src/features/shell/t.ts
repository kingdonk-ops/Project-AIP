/**
 * Terminology lookup for the shell (DESIGN-02). Reads `config/terms/en-AU/*.json` at build time.
 *
 * GAP (TERMS-08): `packages/terms` (the dictionary-backed provider) is not merged yet. When it is,
 * this module re-exports its `t` and call sites do not change. A missing key renders a visible
 * marker and logs a warning; it never renders an empty string.
 */
const modules = import.meta.glob<Record<string, string>>("../../../../../config/terms/en-AU/*.json", {
  eager: true,
  import: "default",
});

const dictionary: Record<string, string> = Object.assign({}, ...Object.values(modules));

export function t(key: string, params?: Record<string, string | number>): string {
  const template = dictionary[key];
  if (template === undefined) {
    console.warn(`Missing terminology key: ${key}`);
    return `⟦${key}⟧`;
  }
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in params ? String(params[name]) : match));
}
