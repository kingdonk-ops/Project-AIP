// @vitest-environment node
import { ESLint } from "eslint";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Lints in-memory source (lintText) against the real config; nothing is written to the tree.
const cwd = fileURLToPath(new URL("..", import.meta.url));
const eslint = new ESLint({ cwd });

async function lint(code: string, filePath = "src/components/__probe__.tsx") {
  const [result] = await eslint.lintText(code, { filePath });
  return (result?.messages ?? []).filter((m) => m.severity === 2).map((m) => m.ruleId);
}

describe("ui lint gate", { timeout: 30_000 }, () => {
  it("rejects a clickable div with no role (jsx-a11y)", async () => {
    const rules = await lint(
      `export function Probe({ onAct }: { onAct: () => void }) {\n  return <div onClick={onAct} />;\n}\n`,
    );
    expect(rules).toContain("jsx-a11y/click-events-have-key-events");
    expect(rules).toContain("jsx-a11y/no-static-element-interactions");
  });

  it("rejects literal text in components", async () => {
    const rules = await lint(`export function Probe() {\n  return <span>Rejected</span>;\n}\n`);
    expect(rules).toContain("react/jsx-no-literals");
  });

  it("rejects imports from apps", async () => {
    const rules = await lint(`import { t } from "../../../../apps/web/src/terms";\nexport const x = t;\n`);
    expect(rules).toContain("boundaries/dependencies");
  });

  it("rejects literal text in feedback and pattern components", async () => {
    for (const filePath of ["src/feedback/__probe__.tsx", "src/patterns/__probe__.tsx"]) {
      const rules = await lint(`export function Probe() {\n  return <span>Rejected</span>;\n}\n`, filePath);
      expect(rules).toContain("react/jsx-no-literals");
    }
  });

  // DESIGN-04: real dialogs and toasts only.
  it("rejects the blocking browser dialogs with a pointer to confirm()/toast()", async () => {
    const [result] = await eslint.lintText(`export function f() {\n  if (confirm("x")) return 1;\n  return 0;\n}\n`, {
      filePath: "src/feedback/__probe__.ts",
    });
    const errors = (result?.messages ?? []).filter((m) => m.severity === 2);
    expect(errors.map((m) => m.ruleId)).toEqual(["no-restricted-globals"]);
    expect(errors[0]?.message).toMatch(/confirm\(\).*@aip\/ui/);

    for (const code of ["window.alert('x');", "window.prompt('x');", "window.confirm('x');", "alert('x');", "prompt('x');"]) {
      const rules = await lint(`export function f() {\n  ${code}\n}\n`, "src/feedback/__probe__.ts");
      expect(rules, code).toEqual([expect.stringMatching(/^no-restricted-(globals|properties)$/)]);
    }
  });

  it("accepts an imported confirm()", async () => {
    const rules = await lint(
      `import { confirm } from "./confirm";\nexport async function f() {\n  return confirm({ titleKey: "a", bodyKey: "b", confirmKey: "c" });\n}\n`,
      "src/feedback/__probe__.ts",
    );
    expect(rules).toEqual([]);
  });

  it("accepts a labelled component taking text through props", async () => {
    const rules = await lint(
      `export function Probe({ label }: { label: string }) {\n  return <button type="button" aria-label={label} />;\n}\n`,
    );
    expect(rules).toEqual([]);
  });
});
