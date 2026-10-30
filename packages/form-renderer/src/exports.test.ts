// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import * as api from "./index";

const indexSource = readFileSync(new URL("index.ts", import.meta.url), "utf8");

/** Names in `export type { ... }` blocks of index.ts. */
function typeExports(): string[] {
  const names: string[] = [];
  for (const m of indexSource.matchAll(/export\s+type\s*\{([^}]*)\}/g)) {
    names.push(
      ...(m[1] ?? "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    );
  }
  return names.sort();
}

describe("@aip/form-renderer public surface", () => {
  it("exports exactly the renderer and the FORMS-02 evaluator at runtime", () => {
    expect(Object.keys(api).sort()).toEqual(
      [
        "ALLOWED_OPERATORS",
        "EVALUATOR_VERSION",
        "FormRenderer",
        "GuardError",
        "evaluateAnswers",
        "evaluateGuard",
        "truthy",
        "validateGuard",
      ].sort(),
    );
  });

  it("exports the adapter types and the FORMS-02 types", () => {
    expect(typeExports()).toEqual(
      [
        "FormRendererProps",
        "MediaAdapter",
        "MediaKind",
        "PickedFile",
        "ReferenceAdapter",
        "ReferenceItem",
        "ReferenceKind",
        "RendererAdapters",
        "EvaluateOptions",
        "AnswerError",
        "AnswerEvaluation",
        "Answers",
        "AnswerValue",
        "EvaluationContext",
        "EvaluationMode",
        "ExpressionError",
        "ExpressionKind",
        "FieldOption",
        "FieldType",
        "FieldValidations",
        "FormField",
        "FormRule",
        "FormSchema",
        "FormSection",
        "Json",
      ].sort(),
    );
  });

  it("has no network code: no fetch, XMLHttpRequest or WebSocket in the package sources", async () => {
    const { readdirSync } = await import("node:fs");
    const root = new URL("./", import.meta.url);
    const files = (readdirSync(root, { recursive: true }) as string[]).filter(
      (f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) && !f.startsWith("test"),
    );
    expect(files.length).toBeGreaterThan(10);
    for (const file of files) {
      const source = readFileSync(new URL(file, root), "utf8");
      expect(source, file).not.toMatch(/\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon/);
    }
  });
});
