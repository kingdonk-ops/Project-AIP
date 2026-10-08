import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Combobox, type ComboboxOption } from "./combobox";

const options: ComboboxOption[] = [
  { value: "p1", label: "Pump P-101" },
  { value: "v1", label: "Valve V-201" },
  { value: "t1", label: "Tank T-301" },
];

function Controlled() {
  const [value, setValue] = useState<string | null>(null);
  return <Combobox aria-label="Asset" options={options} value={value} onValueChange={setValue} />;
}

describe("Combobox", () => {
  it("filters options and selects with the keyboard", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByRole("combobox", { name: "Asset" });
    await user.click(input);
    expect(input.getAttribute("aria-expanded")).toBe("true");
    await user.type(input, "valve");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Valve V-201"]);
    await user.keyboard("{Enter}");
    expect((input as HTMLInputElement).value).toBe("Valve V-201");
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("moves the active option with arrow keys and closes on Escape", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByRole("combobox", { name: "Asset" });
    await user.click(input);
    await user.keyboard("{ArrowDown}");
    expect(input.getAttribute("aria-activedescendant")).toMatch(/-1$/);
    await user.keyboard("{ArrowUp}{Escape}");
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("has no serious or critical axe violations (open and closed)", async () => {
    const { container } = render(<Controlled />);
    expect(await axeBlocking(container)).toEqual([]);
    await userEvent.click(screen.getByRole("combobox"));
    expect(await axeBlocking(container)).toEqual([]);
  });
});
