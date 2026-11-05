import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { FormField } from "./form-field";
import { NativeSelect, Textarea } from "./native-controls";

describe("NativeSelect and Textarea", () => {
  it("carry the input look and take their accessible name from a FormField label", () => {
    render(
      <>
        <FormField label="Site">
          {(control) => (
            <NativeSelect {...control} className="extra" defaultValue="b">
              <option value="a">A</option>
              <option value="b">B</option>
            </NativeSelect>
          )}
        </FormField>
        <FormField label="Reason" error="Too long">
          {(control) => <Textarea {...control} rows={3} />}
        </FormField>
      </>,
    );
    const select = screen.getByRole("combobox", { name: "Site" });
    expect(select.tagName).toBe("SELECT");
    expect(select.className).toContain("aip-input");
    expect(select.className).toContain("aip-native-select");
    expect(select.className).toContain("extra");
    expect((select as HTMLSelectElement).value).toBe("b");
    const textarea = screen.getByRole("textbox", { name: "Reason" });
    expect(textarea.tagName).toBe("TEXTAREA");
    expect(textarea.className).toContain("aip-textarea");
    expect(textarea.getAttribute("aria-invalid")).toBe("true");
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(
      <div>
        <FormField label="Site">
          {(control) => (
            <NativeSelect {...control}>
              <option value="">None</option>
            </NativeSelect>
          )}
        </FormField>
        <FormField label="Reason">{(control) => <Textarea {...control} />}</FormField>
      </div>,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });
});
