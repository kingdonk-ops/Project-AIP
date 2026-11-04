import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Button } from "./button";
import { Panel } from "./panel";

describe("Panel", () => {
  it("renders a section named by its heading, with an actions slot", () => {
    render(
      <Panel heading="Sites" actions={<Button>Add</Button>}>
        <p>body</p>
      </Panel>,
    );
    const region = screen.getByRole("region", { name: "Sites" });
    expect(region.tagName).toBe("SECTION");
    expect(region.className).toContain("aip-panel");
    expect(screen.getByRole("heading", { level: 2, name: "Sites" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add" })).toBeTruthy();
  });

  it("honours a heading level and renders no header row without heading or actions", () => {
    const { container, rerender } = render(<Panel heading="Answers" headingLevel={3} />);
    expect(screen.getByRole("heading", { level: 3, name: "Answers" })).toBeTruthy();
    rerender(<Panel data-testid="bare">x</Panel>);
    expect(container.querySelector(".aip-panel__header")).toBeNull();
    expect(container.querySelector("section")?.hasAttribute("aria-labelledby")).toBe(false);
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(
      <Panel heading="Register" actions={<Button>Export</Button>}>
        <p>content</p>
      </Panel>,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });
});
