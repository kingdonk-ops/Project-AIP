// @vitest-environment node
import { describe, expect, it } from "vitest";
import { MIN_TEXT_CONTRAST, contrastRatio, isAccessibleAccent, relativeLuminance } from "./contrast";

describe("contrastRatio", () => {
  it("matches WCAG 2.x for the AIP teal accent on white", () => {
    expect(contrastRatio("#0f766e", "#ffffff")).toBeCloseTo(5.47, 2);
  });

  it("matches WCAG 2.x for Kaefer red on white", () => {
    expect(contrastRatio("#da291c", "#ffffff")).toBeCloseTo(4.87, 2);
  });

  it("is symmetric and spans 1..21", () => {
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 5);
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#777", "#777777")).toBe(1);
  });

  it("rejects invalid colours", () => {
    expect(() => contrastRatio("teal", "#fff")).toThrow(/invalid hex/);
  });

  it("exposes luminance endpoints", () => {
    expect(relativeLuminance("#000000")).toBe(0);
    expect(relativeLuminance("#ffffff")).toBeCloseTo(1, 10);
  });
});

describe("isAccessibleAccent", () => {
  it("rejects yellow (about 1.4:1)", () => {
    expect(contrastRatio("#ffd400", "#ffffff")).toBeCloseTo(1.43, 1);
    expect(isAccessibleAccent("#ffd400")).toBe(false);
  });

  it("accepts the default teal", () => {
    expect(isAccessibleAccent("#0f766e")).toBe(true);
  });

  it("checks against a custom surface too", () => {
    expect(isAccessibleAccent("#da291c", "#ffffff")).toBe(true);
    expect(isAccessibleAccent("#da291c", "#404040")).toBe(false);
    expect(MIN_TEXT_CONTRAST).toBe(4.5);
  });
});
