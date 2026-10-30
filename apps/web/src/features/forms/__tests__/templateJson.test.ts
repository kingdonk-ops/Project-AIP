import { describe, expect, it } from "vitest";
import { formatPath, lintIssues, requestIssues } from "../issues";
import { validateTemplateSearch, toListParams, templatesQuery } from "../search";
import { lineColumn, parseTemplateJson } from "../templateJson";

describe("parseTemplateJson", () => {
  it("reads a revision schema", () => {
    const result = parseTemplateJson('{"schemaVersion":1,"sections":[]}');
    expect(result).toEqual({ ok: true, schema: { schemaVersion: 1, sections: [] }, meta: {} });
  });

  it("reads an upload body and returns its other keys as meta", () => {
    const result = parseTemplateJson(
      '{"code":"x","name":"X","kind":"itp","schema":{"schemaVersion":1,"sections":[]}}',
    );
    expect(result).toEqual({
      ok: true,
      schema: { schemaVersion: 1, sections: [] },
      meta: { code: "x", name: "X", kind: "itp" },
    });
  });

  it("ignores a kind the API does not know", () => {
    const result = parseTemplateJson('{"kind":"audit","schema":{"sections":[]}}');
    expect(result.ok && result.meta).toEqual({});
  });

  it("reports a parse error with a 1-based line and column", () => {
    const result = parseTemplateJson('{"sections": [}');
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.messageKey).toBe("forms.templates.json.parse_error");
    expect(result.error.line).toBe(1);
    expect(result.error.column).toBeGreaterThanOrEqual(1);
  });

  it("finds the line of an error further down", () => {
    const result = parseTemplateJson('{\n  "sections": [\n    oops\n  ]\n}');
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.line).toBe(3);
  });

  it("refuses JSON that is not a template", () => {
    for (const text of ["[1]", '{"a":1}', "42", '{"schema": [1]}']) {
      const result = parseTemplateJson(text);
      expect(result.ok ? null : result.error.messageKey).toBe("forms.templates.json.not_a_template");
    }
  });

  it("asks for JSON when the text is blank", () => {
    const result = parseTemplateJson("  ");
    expect(result.ok ? null : result.error.messageKey).toBe("forms.templates.json.empty");
  });

  it("maps an offset to line and column", () => {
    expect(lineColumn("ab\ncd", 4)).toEqual({ line: 2, column: 2 });
    expect(lineColumn("ab", 0)).toEqual({ line: 1, column: 1 });
  });
});

describe("issues", () => {
  it("formats a lint path", () => {
    expect(formatPath(["sections", 0, "fields", 2, "key"])).toBe("sections[0].fields[2].key");
    expect(formatPath([])).toBe("");
  });

  it("reads lint issues and request-validation detail", () => {
    expect(lintIssues({ code: "TEMPLATE_INVALID", issues: [{ path: ["sections", 0], code: "DUPLICATE_KEY", message: "m" }] })).toEqual([
      { path: ["sections", 0], code: "DUPLICATE_KEY", message: "m" },
    ]);
    expect(lintIssues({ code: "X" })).toEqual([]);
    expect(requestIssues({ detail: [{ loc: ["body", "code"], msg: "bad", type: "string_pattern_mismatch" }] })).toEqual([
      { path: ["code"], code: "string_pattern_mismatch", message: "bad" },
    ]);
  });
});

describe("search", () => {
  it("keeps only valid detail search values", () => {
    expect(validateTemplateSearch({ tab: "compare", from: "1", to: 2, rev: "x", other: "y" })).toEqual({
      tab: "compare",
      from: 1,
      to: 2,
    });
    expect(validateTemplateSearch({ tab: "usage", rev: "0" })).toEqual({});
  });

  it("maps the register filters to list parameters", () => {
    expect(toListParams(templatesQuery({ kind: "itp", q: "coat" }))).toEqual({ kind: "itp", q: "coat", limit: 200 });
    expect(toListParams(templatesQuery({ kind: "nope" }))).toEqual({ limit: 200 });
  });
});
