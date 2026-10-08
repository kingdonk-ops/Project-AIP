import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "./table";

function Fixture() {
  return (
    <Table>
      <TableCaption>{"Open NCRs"}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>{"ID"}</TableHead>
          <TableHead>{"Title"}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          <TableCell>{"NCR-12"}</TableCell>
          <TableCell>{"Weld defect"}</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  );
}

describe("Table", () => {
  it("renders a captioned table with column headers", () => {
    render(<Fixture />);
    expect(screen.getByRole("table", { name: "Open NCRs" })).toBeTruthy();
    expect(screen.getAllByRole("columnheader").map((h) => h.getAttribute("scope"))).toEqual(["col", "col"]);
    expect(screen.getByRole("cell", { name: "NCR-12" }).className).toContain("aip-table__cell");
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Fixture />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
