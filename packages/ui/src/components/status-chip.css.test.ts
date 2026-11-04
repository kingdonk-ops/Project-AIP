// @vitest-environment node
// DESIGN-09: chip colours live in components.css, which jsdom cannot cascade, so the rules are read here.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { statusTones } from "../tokens/tokens";

const css = readFileSync(new URL("./components.css", import.meta.url), "utf8");

function rule(selector: string): string {
  const escaped = selector.replace(/[.[\]"=-]/g, (c) => `\\${c}`);
  const match = new RegExp(`(^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  if (!match?.[2]) throw new Error(`rule ${selector} not found in components.css`);
  return match[2];
}

describe("status chip colours", () => {
  it.each(statusTones)("%s: tinted fill with the full-strength tone on text and icon", (tone) => {
    const body = rule(`.aip-status-chip--${tone}`);
    expect(body).toContain(`background: var(--status-${tone}-subtle)`);
    expect(body).toContain(`color: var(--status-${tone})`);
  });

  it.each(statusTones)("%s: solid background class under high contrast", (tone) => {
    const body = rule(`[data-contrast="high"] .aip-status-chip--${tone}`);
    expect(body).toContain(`background: var(--status-${tone})`);
    expect(body).toContain("color: var(--status-foreground)");
  });

  it("never fills a surface with the accent outside primary actions and selection", () => {
    const fills = [...css.matchAll(/([^{}]+)\{[^}]*background:\s*var\(--accent\)/g)].map((m) => (m[1] ?? "").trim());
    expect(fills).toEqual([".aip-button--primary", '.aip-checkbox[data-state="checked"],\n.aip-checkbox[data-state="indeterminate"]']);
  });
});
