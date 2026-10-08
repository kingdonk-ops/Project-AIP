import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Input } from "./input";

describe("Input", () => {
  it("renders a text input with token styling", () => {
    render(<Input aria-label="Name" defaultValue="x" />);
    const input = screen.getByRole("textbox", { name: "Name" });
    expect(input.getAttribute("type")).toBe("text");
    expect(input.className).toContain("aip-input");
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Input aria-label="Name" />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
