import { describe, expect, it } from "vitest";
import { canonical, diffSchemas } from "../diff";
import { jsonErrorOffset } from "../templateJson";
import { V1, V2 } from "./fixtures";

describe("diffSchemas", () => {
  it("finds added, moved and changed fields", () => {
    const { changes, counts } = diffSchemas(V1, V2);
    expect(counts).toEqual({ added: 1, removed: 0, changed: 1, moved: 1 });

    const added = changes.find((c) => c.key === "blast_standard");
    expect(added).toMatchObject({ item: "field", change: "added", section: "prep" });

    const moved = changes.find((c) => c.key === "surface_prepared");
    expect(moved).toMatchObject({ item: "field", change: "moved", fromSection: "prep", toSection: "final" });
    expect(moved?.properties).toEqual([]);

    const changed = changes.find((c) => c.key === "dft_avg");
    expect(changed).toMatchObject({ item: "field", change: "changed", section: "prep" });
    expect(changed?.properties).toEqual([
      { name: "required", before: undefined, after: true },
      { name: "unit", before: "mm", after: "um" },
    ]);
  });

  it("reports a removed section and each of its fields", () => {
    const to = { schemaVersion: 1, sections: [V1.sections[0]!] };
    const { changes, counts } = diffSchemas(V1, to);
    expect(counts).toEqual({ added: 0, removed: 2, changed: 0, moved: 0 });
    expect(changes.map((c) => [c.item, c.key, c.change])).toEqual([
      ["section", "final", "removed"],
      ["field", "remarks", "removed"],
    ]);
  });

  it("ignores key order inside the JSON", () => {
    const reordered = JSON.parse(
      JSON.stringify(V1, (_key, value: unknown) =>
        value && typeof value === "object" && !Array.isArray(value)
          ? Object.fromEntries(Object.entries(value as Record<string, unknown>).reverse())
          : value,
      ),
    ) as typeof V1;
    expect(diffSchemas(V1, reordered).changes).toEqual([]);
  });

  it("shows a changed condition as a property change", () => {
    const to = structuredClone(V1);
    (to.sections[1]!.fields[0] as Record<string, unknown>).visibleIf = {
      "==": [{ var: "answers.surface_prepared" }, false],
    };
    const { changes } = diffSchemas(V1, to);
    expect(changes).toHaveLength(1);
    expect(changes[0]).toMatchObject({ key: "remarks", change: "changed" });
    expect(changes[0]!.properties.map((p) => p.name)).toEqual(["visibleIf"]);
  });

  it("reports a field that changed position within its section", () => {
    const to = structuredClone(V1);
    to.sections[0]!.fields.reverse();
    const { counts, changes } = diffSchemas(V1, to);
    expect(counts.moved).toBe(2);
    expect(changes.every((c) => c.reordered)).toBe(true);
  });

  it("reports a top-level change as a template change", () => {
    const { changes } = diffSchemas(V1, { ...V1, schemaVersion: 2 });
    expect(changes).toEqual([
      { item: "template", key: "", change: "changed", properties: [{ name: "schemaVersion", before: 1, after: 2 }] },
    ]);
  });

  it("canonical JSON sorts object keys", () => {
    expect(canonical({ b: 1, a: [{ d: 1, c: 2 }] })).toBe('{"a":[{"c":2,"d":1}],"b":1}');
  });
});

describe("jsonErrorOffset", () => {
  it("is -1 for valid JSON and points at the first error otherwise", () => {
    expect(jsonErrorOffset('{"a": [1, true, null, "x\\n"]}')).toBe(-1);
    expect(jsonErrorOffset('{"a":}')).toBe(5);
    expect(jsonErrorOffset('{"a":1,}')).toBe(7);
    expect(jsonErrorOffset('{"a":1} x')).toBe(8);
  });
});
