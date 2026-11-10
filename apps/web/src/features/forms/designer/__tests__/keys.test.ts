import { describe, expect, it } from "vitest";
import { isValidKey, keyFromLabel } from "../keys";

describe("keyFromLabel", () => {
  it("lower-cases and turns other characters into underscores", () => {
    expect(keyFromLabel("Surface Prep. (ISO 8501)", [])).toBe("surface_prep_iso_8501");
  });

  it("prefixes a leading digit", () => {
    expect(keyFromLabel("2nd coat", [])).toBe("f_2nd_coat");
  });

  it("de-duplicates against taken keys", () => {
    expect(keyFromLabel("Remarks", ["remarks"])).toBe("remarks_2");
    expect(keyFromLabel("Remarks", ["remarks", "remarks_2"])).toBe("remarks_3");
  });

  it("keeps a long label within 63 characters and valid", () => {
    const label = "A very long label ".repeat(6).slice(0, 100);
    const key = keyFromLabel(label, []);
    expect(key.length).toBeLessThanOrEqual(63);
    expect(isValidKey(key)).toBe(true);
    const second = keyFromLabel(label, [key]);
    expect(second.length).toBeLessThanOrEqual(63);
    expect(isValidKey(second)).toBe(true);
    expect(second).not.toBe(key);
  });

  it("falls back to a valid key for a label with no letters or digits", () => {
    expect(isValidKey(keyFromLabel("—", []))).toBe(true);
  });

  it("strips accents", () => {
    expect(keyFromLabel("Épaisseur", [])).toBe("epaisseur");
  });
});
