import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { FormField } from "./form-field";
import { Input } from "./input";

describe("FormField", () => {
  it("wires label, hint and error to the control", () => {
    render(
      <FormField label="Tag" hint="Plant tag number" error="Required">
        {(control) => <Input {...control} />}
      </FormField>,
    );
    const input = screen.getByLabelText("Tag");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const describedBy = input.getAttribute("aria-describedby")?.split(" ") ?? [];
    expect(describedBy).toHaveLength(2);
    expect(describedBy.map((id) => document.getElementById(id)?.textContent)).toEqual(["Plant tag number", "Required"]);
    expect(screen.getByRole("alert").textContent).toBe("Required");
  });

  it("omits aria-describedby and aria-invalid when there is no hint or error", () => {
    render(<FormField label="Tag">{(control) => <Input {...control} />}</FormField>);
    const input = screen.getByLabelText("Tag");
    expect(input.hasAttribute("aria-describedby")).toBe(false);
    expect(input.hasAttribute("aria-invalid")).toBe(false);
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(
      <FormField label="Tag" hint="Plant tag number" error="Required">
        {(control) => <Input {...control} />}
      </FormField>,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });
});
