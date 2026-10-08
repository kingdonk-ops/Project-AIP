import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";

function Fixture({ open }: { open?: boolean }) {
  return (
    <Select defaultValue="open" {...(open === undefined ? {} : { open })}>
      <SelectTrigger aria-label="Status">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="open">{"Open"}</SelectItem>
        <SelectItem value="closed">{"Closed"}</SelectItem>
      </SelectContent>
    </Select>
  );
}

describe("Select", () => {
  it("renders a named combobox trigger showing the selected value", () => {
    render(<Fixture />);
    const trigger = screen.getByRole("combobox", { name: "Status" });
    expect(trigger.textContent).toContain("Open");
    expect(trigger.className).toContain("aip-select__trigger");
  });

  it("lists options when open", () => {
    render(<Fixture open />);
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(screen.getByRole("option", { name: "Closed" })).toBeTruthy();
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Fixture />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
