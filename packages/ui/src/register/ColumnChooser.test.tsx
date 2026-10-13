import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { ColumnChooser, defaultColumns, localStorageColumnPrefs } from "./ColumnChooser";
import { columns, t } from "./fixture";

afterEach(() => localStorage.clear());

describe("ColumnChooser", () => {
  it("defaults to every column not marked hidden", () => {
    expect(defaultColumns([...columns, { id: "x", headerKey: "x", cell: () => null, defaultVisible: false }])).toEqual([
      "code",
      "name",
      "region",
    ]);
  });

  it("keeps preferences per register in local storage", () => {
    expect(localStorageColumnPrefs.get("projects")).toBeNull();
    localStorageColumnPrefs.set("projects", ["code"]);
    expect(localStorageColumnPrefs.get("projects")).toEqual(["code"]);
    localStorageColumnPrefs.set("projects", null);
    expect(localStorageColumnPrefs.get("projects")).toBeNull();
    localStorage.setItem("aip.register.columns.bad", "{oops");
    expect(localStorageColumnPrefs.get("bad")).toBeNull();
  });

  it("never hides the last column", async () => {
    const changes: (readonly string[] | null)[] = [];
    const { container } = render(
      <ColumnChooser columns={columns} visible={["code"]} onChange={(v) => changes.push(v)} translate={t} />,
    );
    await userEvent.click(screen.getByText("Columns", { selector: "summary" }));
    expect(screen.getByRole("checkbox", { name: "Code" })).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByRole("checkbox", { name: "Name" }));
    expect(changes).toEqual([["code", "name"]]);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
