// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { aipPreset } from "../../tailwind-preset";
import { isAccessibleAccent } from "./contrast";
import { colors, cssVar, density, fontSize, fonts, radii, rootTokens, spacing, statusTones } from "./tokens";

const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

function block(selector: string): Record<string, string> {
  const escaped = selector.replace(/[[\]"=]/g, (c) => `\\${c}`);
  const match = new RegExp(`(^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  if (!match?.[2]) throw new Error(`selector ${selector} not found in tokens.css`);
  const vars: Record<string, string> = {};
  for (const m of match[2].matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    if (m[1] && m[2]) vars[m[1]] = m[2].trim();
  }
  return vars;
}

describe("design tokens", () => {
  const root = block(":root");

  it("tokens.ts mirrors every :root value in tokens.css", () => {
    for (const [name, value] of Object.entries(rootTokens)) {
      expect(root[name], `--${name}`).toBe(value);
    }
  });

  it("defines the accent as a single variable with the AIP teal default", () => {
    expect(root["accent"]).toBe("#0f766e");
    expect(colors.accent).toBe("#0f766e");
    expect(root["accent-foreground"]).toBe("#ffffff");
  });

  it("uses the required type scale, 4px spacing grid and radii", () => {
    expect(Object.values(fontSize)).toEqual(["12px", "13px", "14px", "16px", "20px", "24px", "30px"]);
    for (const v of Object.values(spacing)) expect(parseInt(v, 10) % 4).toBe(0);
    expect(Object.values(radii)).toEqual(["2px", "4px", "8px"]);
  });

  it("has compact, comfortable, field and high-contrast themes", () => {
    expect(root["row-h"]).toBe(density.compact["row-h"]);
    expect(block('[data-density="comfortable"]')["row-h"]).toBe("40px");
    expect(block("[data-field]")["touch-target"]).toBe("48px");
    expect(Object.keys(block('[data-contrast="high"]'))).toContain("accent");
  });

  it("keeps every status and high-contrast colour readable with white text", () => {
    for (const tone of statusTones) expect(isAccessibleAccent(colors[`status-${tone}`])).toBe(true);
    for (const [name, value] of Object.entries(block('[data-contrast="high"]'))) {
      if (name === "accent" || (name.startsWith("status-") && name !== "status-foreground")) {
        expect(isAccessibleAccent(value), name).toBe(true);
      }
    }
  });

  it("self-hosts IBM Plex 400/500/600 and never references Google Fonts", () => {
    for (const family of ["ibm-plex-sans", "ibm-plex-mono"]) {
      for (const weight of [400, 500, 600]) {
        expect(css).toContain(`@import "@fontsource/${family}/${weight}.css";`);
      }
    }
    expect(css).not.toMatch(/fonts\.(googleapis|gstatic)\.com/);
    expect(fonts.sans.startsWith('"IBM Plex Sans"')).toBe(true);
    expect(fonts.mono.startsWith('"IBM Plex Mono"')).toBe(true);
  });

  it("cssVar references the runtime variable", () => {
    expect(cssVar("accent")).toBe("var(--accent)");
  });

  it("tailwind preset maps to CSS variables, never hex values", () => {
    const serialised = JSON.stringify(aipPreset);
    expect(serialised).not.toMatch(/#[0-9a-f]{3,6}\b/i);
    expect(aipPreset.theme.extend.colors.accent).toBe("var(--accent)");
    expect(aipPreset.theme.extend.fontSize.base).toBe("var(--text-base)");
  });
});
