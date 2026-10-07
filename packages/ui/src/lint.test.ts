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
    const rules = await lint(`import { t } from "../../../apps/web/src/terms";\nexport const x = t;\n`);
    expect(rules).toContain("no-restricted-imports");
  });

  it("accepts a labelled component taking text through props", async () => {
    const rules = await lint(
      `export function Probe({ label }: { label: string }) {\n  return <button type="button" aria-label={label} />;\n}\n`,
    );
    expect(rules).toEqual([]);
  });
});
