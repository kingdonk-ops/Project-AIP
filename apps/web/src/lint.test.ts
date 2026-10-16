// @vitest-environment node
import { ESLint } from "eslint";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// DESIGN-04: apps/web extends the @aip/ui dialog ban. Lints in-memory source against the real config.
const cwd = fileURLToPath(new URL("..", import.meta.url));
const eslint = new ESLint({ cwd });

async function errors(code: string) {
  const [result] = await eslint.lintText(code, { filePath: "src/features/projects/__probe__.tsx" });
  return (result?.messages ?? []).filter((m) => m.severity === 2);
}

describe("web lint: blocking dialogs", { timeout: 60_000 }, () => {
  it("rejects window.alert on a page", async () => {
    const found = await errors(`export function f() {\n  window.alert("x");\n}\n`);
    expect(found.map((m) => m.ruleId)).toEqual(["no-restricted-properties"]);
    expect(found[0]?.message).toMatch(/toast\(\)/);
  });

  it("rejects a bare confirm()", async () => {
    const found = await errors(`export function f() {\n  return confirm("x");\n}\n`);
    expect(found.map((m) => m.ruleId)).toEqual(["no-restricted-globals"]);
  });

  it("accepts confirm() imported from @aip/ui", async () => {
    const found = await errors(
      `import { confirm } from "@aip/ui";\nexport function f() {\n  return confirm({ titleKey: "a", bodyKey: "b", confirmKey: "c" });\n}\n`,
    );
    expect(found).toEqual([]);
  });
});
