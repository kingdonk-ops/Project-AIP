import { describe, expect, it } from "vitest";
import { elementOffset, formatAttributes, issueIndex, lineColumn, parseAttributes } from "../attributes";
import { ATTRIBUTE_FIELD_TYPES } from "../fieldTypes";

describe("parseAttributes", () => {
  it("accepts a valid attribute list with no hints", () => {
    const result = parseAttributes('[{"key":"a","label":"A","fieldType":"text"}]');
    expect(result).toEqual({ ok: true, attributes: [{ key: "a", label: "A", fieldType: "text" }], hints: [] });
  });

  it("reports a JSON syntax error with a 1-based line and column, and no hints", () => {
    const result = parseAttributes('[{"key":"a",}]');
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.line).toBe(1);
    expect(result.error.column).toBeGreaterThanOrEqual(1);
    expect(result.hints).toEqual([]);
  });

  it("finds the line of an error on a later line", () => {
    const result = parseAttributes('[\n  {"key": "a"},\n  {"key": }\n]');
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.line).toBe(3);
  });

  it("hints when the value is not an array", () => {
    const result = parseAttributes('{"key":"a"}');
    expect(result.ok && result.hints).toEqual([{ key: "item_types.hint.not_an_array" }]);
  });

  it("hints a duplicate key at the second attribute", () => {
    const result = parseAttributes('[{"key":"a","fieldType":"text"},{"key":"a","fieldType":"number"}]');
    expect(result.ok && result.hints).toEqual([{ key: "item_types.hint.duplicate_key", index: 1 }]);
  });

  it("hints a field type that is not usable as an attribute", () => {
    const result = parseAttributes('[{"key":"p","fieldType":"photo"}]');
    expect(result.ok && result.hints).toEqual([{ key: "item_types.hint.field_type_not_allowed", index: 0 }]);
  });

  it("hints an unknown field type and an item that is not an object", () => {
    const result = parseAttributes('[{"key":"g","fieldType":"gps"}, 3]');
    expect(result.ok && result.hints).toEqual([
      { key: "item_types.hint.field_type_unknown", index: 0 },
      { key: "item_types.hint.not_an_object", index: 1 },
    ]);
  });
});

describe("attribute helpers", () => {
  it("offers only field types usable in attributes", () => {
    const keys = ATTRIBUTE_FIELD_TYPES.map((f) => f.key);
    expect(keys).toContain("measurement");
    expect(keys).not.toContain("photo");
    expect(keys).not.toContain("signature");
  });

  it("pretty-prints with two spaces", () => {
    expect(formatAttributes([{ key: "a" }])).toBe('[\n  {\n    "key": "a"\n  }\n]');
  });

  it("reads the attribute index from an issue path", () => {
    expect(issueIndex("attributes[0].config")).toBe(0);
    expect(issueIndex("attributes[12].key")).toBe(12);
    expect(issueIndex("attributes")).toBeUndefined();
  });

  it("finds where each top-level element starts, skipping brackets inside strings", () => {
    const text = '[\n  {"key": "a[,]"},\n  {"key": "b"}\n]';
    expect(text.slice(elementOffset(text, 0), elementOffset(text, 0) + 4)).toBe('{"ke');
    expect(text.slice(elementOffset(text, 1))).toMatch(/^\{"key": "b"\}/);
    expect(elementOffset(text, 5)).toBe(0);
    expect(elementOffset("[]", 0)).toBe(0);
  });

  it("converts offsets to lines and columns", () => {
    expect(lineColumn("ab\ncd", 4)).toEqual({ line: 2, column: 2 });
  });
});
