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

  it("renders a decorative leading icon and keeps the accessible name from its label", () => {
    const { container } = render(
      <>
        <label htmlFor="q">Search</label>
        <Input id="q" type="search" icon="search" />
      </>,
    );
    const input = screen.getByRole("searchbox", { name: "Search" });
    expect(input.className).toContain("aip-input--with-icon");
    const svg = container.querySelector(".aip-input-wrap svg");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(input.parentElement?.className).toBe("aip-input-wrap");
  });

  it("renders no wrapper without an icon", () => {
    const { container } = render(<Input aria-label="Name" />);
    expect(container.querySelector(".aip-input-wrap")).toBeNull();
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(
      <div>
        <Input aria-label="Name" />
        <Input aria-label="Search" type="search" icon="search" />
      </div>,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });
});
