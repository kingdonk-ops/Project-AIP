// @vitest-environment node
import { describe, expect, it } from "vitest";
import { cn } from "./cn";

describe("cn", () => {
  it("joins truthy class names and drops falsy ones", () => {
    expect(cn("aip-button", false, null, undefined, "extra")).toBe("aip-button extra");
  });

  it("lets later Tailwind utilities win", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });
});
