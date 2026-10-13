import { describe, expect, it } from "vitest";
import { DEFAULT_PAGE_SIZE, PAGE_SIZES } from "./types";

describe("register defaults", () => {
  it("offers 25, 50 and 100 rows per page and defaults to 50", () => {
    expect(PAGE_SIZES).toEqual([25, 50, 100]);
    expect(DEFAULT_PAGE_SIZE).toBe(50);
  });
});
