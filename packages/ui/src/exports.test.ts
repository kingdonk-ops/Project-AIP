// @vitest-environment node
import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import * as api from "./index";

const srcDir = new URL("./", import.meta.url);
const indexSource = readFileSync(new URL("index.ts", srcDir), "utf8");

/** Runtime (non-type) export names per module, parsed from `export { ... } from "./x"` in index.ts. */
function exportsByModule(): Map<string, string[]> {
  const result = new Map<string, string[]>();
  for (const m of indexSource.matchAll(/export\s*\{([^}]*)\}\s*from\s*"(\.\/[^"]+)"/g)) {
    const names = (m[1] ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s && !s.startsWith("type "));
    result.set(m[2] ?? "", names);
  }
  return result;
}

function testFileFor(modulePath: string): string | null {
  for (const ext of [".test.tsx", ".test.ts"]) {
    const url = new URL(`${modulePath}${ext}`, srcDir);
    if (existsSync(url)) return readFileSync(url, "utf8");
  }
  return null;
}

describe("index.ts exports", () => {
  const modules = exportsByModule();

  it("parses every runtime export of the package", () => {
    const parsed = [...modules.values()].flat().sort();
    expect(parsed).toEqual(Object.keys(api).sort());
  });

  it.each([...modules.keys()])("%s has a matching test file that covers each export", (modulePath) => {
    const source = testFileFor(modulePath);
    expect(source, `missing ${modulePath}.test.ts(x)`).not.toBeNull();
    for (const name of modules.get(modulePath) ?? []) {
      expect(new RegExp(`\\b${name}\\b`).test(source ?? ""), `${name} is not exercised in ${modulePath} test`).toBe(true);
    }
  });

  it("every component test runs axe", () => {
    for (const modulePath of modules.keys()) {
      if (!modulePath.startsWith("./components/")) continue;
      expect(testFileFor(modulePath), modulePath).toMatch(/axeBlocking\(/);
    }
  });
});
