import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Checkbox } from "./checkbox";
import { Label } from "./label";

describe("Checkbox", () => {
  it("toggles and exposes its checked state", async () => {
    render(
      <div>
        <Checkbox id="agree" />
        <Label htmlFor="agree">{"Agree"}</Label>
      </div>,
    );
    const box = screen.getByRole("checkbox", { name: "Agree" });
    expect(box.getAttribute("aria-checked")).toBe("false");
    await userEvent.click(box);
    expect(box.getAttribute("aria-checked")).toBe("true");
  });

  it("supports the indeterminate state", () => {
    render(<Checkbox aria-label="All" checked="indeterminate" />);
    expect(screen.getByRole("checkbox", { name: "All" }).getAttribute("aria-checked")).toBe("mixed");
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Checkbox aria-label="Agree" defaultChecked />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
