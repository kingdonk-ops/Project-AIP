import type { FormSchema } from "@aip/form-renderer";
import { describe, expect, it } from "vitest";
import {
  addField,
  addSection,
  allKeys,
  changeFieldType,
  FORM_FIELD_TYPES,
  issueCounts,
  issueTarget,
  keyError,
  MEASUREMENT_UNITS,
  moveField,
  moveSection,
  removeField,
  removeSection,
  renameKey,
  setValidation,
  updateField,
  updateSection,
} from "../model";

function schema(): FormSchema {
  return {
    schemaVersion: 2,
    sections: [
      {
        key: "prep",
        label: "Preparation",
        fields: [
          { key: "surface_prepared", type: "boolean", label: "Surface prepared" },
          {
            key: "blast_standard",
            type: "dropdown",
            label: "Blast standard",
            options: [{ value: "sa2_5", label: "Sa 2.5" }],
            visibleIf: { "==": [{ var: "answers.surface_prepared" }, true] },
          },
          { key: "dft_avg", type: "measurement", label: "DFT", unit: "mm", validations: { min: 0.25 } },
        ],
        rules: [{ key: "prep_ok", expr: { "==": [{ var: "answers.surface_prepared" }, true] }, label: "Prepared" }],
        // An unknown property must survive every operation.
        "x-note": "keep me",
      } as FormSchema["sections"][number],
      { key: "final", label: "Final", fields: [{ key: "remarks", type: "text", label: "Remarks" }] },
    ],
  };
}

function frozen(): FormSchema {
  const s = schema();
  return JSON.parse(JSON.stringify(s)) as FormSchema;
}

describe("designer model", () => {
  it("offers the 12 form field types and the lint's units", () => {
    expect(FORM_FIELD_TYPES).toHaveLength(12);
    expect(MEASUREMENT_UNITS).toContain("mm");
  });

  it("adds a dropdown at an index with one option", () => {
    const { schema: next, key } = addField(schema(), "dropdown", "prep", 1, { field: "Coat", option: "Option 1" });
    const field = next.sections[0]!.fields[1]!;
    expect(field.key).toBe(key);
    expect(key).toBe("coat");
    expect(field.options).toEqual([{ value: "option_1", label: "Option 1" }]);
  });

  it("gives a new measurement a unit and keeps keys unique", () => {
    const { schema: next, key } = addField(schema(), "measurement", "final", 99, { field: "Remarks" });
    expect(key).toBe("remarks_2");
    const field = next.sections[1]!.fields[1]!;
    expect(field.unit).toBe(MEASUREMENT_UNITS[0]);
  });

  it("adds a section with a unique key", () => {
    const { schema: next, key } = addSection(schema(), 1, "Final");
    expect(key).toBe("final_2");
    expect(next.sections.map((s) => s.key)).toEqual(["prep", "final_2", "final"]);
  });

  it("moves a field across sections", () => {
    const next = moveField(schema(), "dft_avg", "final", 0);
    expect(next.sections[0]!.fields.map((f) => f.key)).toEqual(["surface_prepared", "blast_standard"]);
    expect(next.sections[1]!.fields.map((f) => f.key)).toEqual(["dft_avg", "remarks"]);
  });

  it("moves a field within a section", () => {
    const next = moveField(schema(), "dft_avg", "prep", 0);
    expect(next.sections[0]!.fields.map((f) => f.key)).toEqual(["dft_avg", "surface_prepared", "blast_standard"]);
  });

  it("reorders sections", () => {
    expect(moveSection(schema(), "final", 0).sections.map((s) => s.key)).toEqual(["final", "prep"]);
  });

  it("changing dropdown to text drops options and keeps visibleIf", () => {
    const next = changeFieldType(schema(), "blast_standard", "text");
    const field = next.sections[0]!.fields[1]!;
    expect(field.type).toBe("text");
    expect(field.options).toBeUndefined();
    expect(field.visibleIf).toEqual({ "==": [{ var: "answers.surface_prepared" }, true] });
  });

  it("changing measurement to number keeps min and drops the unit; to boolean drops validations", () => {
    const asNumber = changeFieldType(schema(), "dft_avg", "number").sections[0]!.fields[2]!;
    expect(asNumber.unit).toBeUndefined();
    expect(asNumber.validations).toEqual({ min: 0.25 });
    const asBoolean = changeFieldType(schema(), "dft_avg", "boolean").sections[0]!.fields[2]!;
    expect(asBoolean.validations).toBeUndefined();
  });

  it("renames a key and rewrites references in visibleIf and section rules", () => {
    const next = renameKey(schema(), "surface_prepared", "surface_ready");
    const prep = next.sections[0]!;
    expect(prep.fields[0]!.key).toBe("surface_ready");
    expect(prep.fields[1]!.visibleIf).toEqual({ "==": [{ var: "answers.surface_ready" }, true] });
    expect(prep.rules![0]!.expr).toEqual({ "==": [{ var: "answers.surface_ready" }, true] });
  });

  it("renames sub-paths and the array form of var", () => {
    const s = updateField(schema(), "remarks", {
      failWhen: { "<": [{ var: ["answers.dft_avg.value", 0] }, 0.25] },
    });
    const next = renameKey(s, "dft_avg", "dft_mean");
    expect(next.sections[1]!.fields[0]!.failWhen).toEqual({ "<": [{ var: ["answers.dft_mean.value", 0] }, 0.25] });
  });

  it("removing a referenced field returns the referencing keys", () => {
    const { schema: next, referencedBy } = removeField(schema(), "surface_prepared");
    expect(referencedBy.sort()).toEqual(["blast_standard", "prep_ok"]);
    expect(allKeys(next)).not.toContain("surface_prepared");
    expect(removeField(schema(), "remarks").referencedBy).toEqual([]);
  });

  it("removing a section reports only references from outside it", () => {
    const s = updateField(schema(), "remarks", { visibleIf: { "==": [{ var: "answers.dft_avg" }, 1] } });
    const { schema: next, referencedBy } = removeSection(s, "prep");
    expect(referencedBy).toEqual(["remarks"]);
    expect(next.sections.map((x) => x.key)).toEqual(["final"]);
  });

  it("sets and clears validations", () => {
    let next = setValidation(schema(), "remarks", "maxLength", 50);
    expect(next.sections[1]!.fields[0]!.validations).toEqual({ maxLength: 50 });
    next = setValidation(next, "remarks", "maxLength", undefined);
    expect(next.sections[1]!.fields[0]!.validations).toBeUndefined();
  });

  it("checks a new key", () => {
    expect(keyError(schema(), "remarks", "Bad Key")).toBe("invalid");
    expect(keyError(schema(), "remarks", "prep")).toBe("taken");
    expect(keyError(schema(), "remarks", "prep_ok")).toBe("taken");
    expect(keyError(schema(), "remarks", "notes")).toBeNull();
  });

  it("maps a lint path to its field or section and counts issues", () => {
    const s = schema();
    expect(issueTarget(s, ["sections", 0, "fields", 1, "unit"])).toEqual({ kind: "field", key: "blast_standard" });
    expect(issueTarget(s, ["sections", 1, "label"])).toEqual({ kind: "section", key: "final" });
    expect(issueTarget(s, ["schemaVersion"])).toBeNull();
    const counts = issueCounts(s, [["sections", 0, "fields", 1, "unit"], ["sections", 0, "fields", 1], ["sections", 1]]);
    expect(counts.get("blast_standard")).toBe(2);
    expect(counts.get("final")).toBe(1);
  });

  it("keeps unknown properties and never mutates its input", () => {
    const input = schema();
    const before = frozen();
    const results = [
      addField(input, "text", "prep", 0, { field: "New" }).schema,
      addSection(input, 0, "New").schema,
      moveField(input, "remarks", "prep", 0),
      moveSection(input, "final", 0),
      removeField(input, "remarks").schema,
      updateField(input, "remarks", { label: "Notes" }),
      updateSection(input, "prep", { label: "Prep" }),
      changeFieldType(input, "blast_standard", "multi_select"),
      renameKey(input, "prep", "preparation"),
      setValidation(input, "dft_avg", "max", 1),
    ];
    expect(input).toEqual(before);
    for (const result of results) {
      const prep = result.sections.find((s) => s.key === "prep" || s.key === "preparation")!;
      expect((prep as unknown as Record<string, unknown>)["x-note"]).toBe("keep me");
    }
  });
});
