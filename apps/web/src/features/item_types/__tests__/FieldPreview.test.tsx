import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { t } from "../../shell/t";
import { FieldPreview } from "../FieldPreview";

const TWO = [
  {
    key: "wall_thickness",
    label: "Wall thickness",
    fieldType: "measurement",
    required: true,
    config: { unit: "mm", min: 0, max: 100 },
  },
  {
    key: "material",
    label: "Material",
    fieldType: "dropdown",
    config: {
      options: [
        { value: "cs", label: "Carbon steel" },
        { value: "ss", label: "Stainless" },
      ],
    },
  },
];

describe("FieldPreview", () => {
  it("lists the attributes in order with label, key, type, required, range and options, and no inputs", () => {
    const { container } = render(<FieldPreview attributes={TWO} />);
    const list = screen.getByRole("list", { name: t("item_types.preview.title") });
    const rows = within(list).getAllByRole("listitem").filter((li) => li.parentElement === list);
    expect(rows).toHaveLength(2);

    const first = within(rows[0]!);
    expect(first.getByText("Wall thickness")).toBeTruthy();
    expect(first.getByText("wall_thickness")).toBeTruthy();
    expect(first.getByText("Measurement")).toBeTruthy();
    expect(first.getByText("Required")).toBeTruthy();
    expect(first.getByText("0–100 mm")).toBeTruthy();

    const second = within(rows[1]!);
    expect(second.getByText("Material")).toBeTruthy();
    expect(second.getByText("Carbon steel")).toBeTruthy();
    expect(second.getByText("Stainless")).toBeTruthy();
    expect(second.queryByText("Required")).toBeNull();

    expect(container.querySelectorAll("input, select, textarea")).toHaveLength(0);
  });

  it("renders a warning row for an unknown field type instead of failing", () => {
    render(<FieldPreview attributes={[{ key: "where", label: "Where", fieldType: "gps" }]} />);
    expect(screen.getByText(t("item_types.preview.unknown_field_type", { fieldType: "gps" }))).toBeTruthy();
  });

  it("shows the range of a decimal and an empty state for no attributes", () => {
    const { unmount } = render(<FieldPreview attributes={[{ key: "d", label: "D", fieldType: "decimal", config: { min: 1, max: 2.5 } }]} />);
    expect(screen.getByText("1–2.5")).toBeTruthy();
    unmount();
    render(<FieldPreview attributes={[]} />);
    expect(screen.getByText(t("item_types.preview.empty"))).toBeTruthy();
  });

  it("never imports the form renderer package", () => {
    const sources = import.meta.glob<string>("../*.{ts,tsx}", { query: "?raw", import: "default", eager: true });
    expect(Object.keys(sources).length).toBeGreaterThan(5);
    for (const [name, source] of Object.entries(sources)) {
      expect(source, name).not.toMatch(/@aip\/form-renderer/);
    }
  });
});
