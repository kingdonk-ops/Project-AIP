import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { Harness, result, rows, type Pages, type Row } from "./fixture";
import { RegisterTable } from "./RegisterTable";
import type { RegisterQuery } from "./types";

const pagesOf =
  (pages: Record<string, { items: Row[]; next: string | null }>, seen: RegisterQuery[] = []): Pages =>
  (query) => {
    seen.push(query);
    const page = pages[query.cursor ?? "first"]!;
    return result({ items: page.items, nextCursor: page.next });
  };

const THREE_PAGES = {
  first: { items: rows(2, 0), next: "c1" },
  c1: { items: rows(2, 2), next: "c2" },
  c2: { items: rows(1, 4), next: null },
};

describe("RegisterTable", () => {
  it("pages forward and back by cursor; Previous is disabled on page 1", async () => {
    const seen: RegisterQuery[] = [];
    render(<Harness pages={pagesOf(THREE_PAGES)} seen={seen} />);
    const previous = screen.getByRole("button", { name: "Previous" });
    expect(previous).toHaveProperty("disabled", true);

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("button", { name: "Next" })).toHaveProperty("disabled", true);
    expect(screen.getAllByRole("row")).toHaveLength(2); // header + the last page's one row

    await userEvent.click(previous);
    expect(seen.at(-1)?.cursor).toBe("c1");
    await userEvent.click(previous);
    expect(seen.at(-1)?.cursor).toBeUndefined();
    expect(previous).toHaveProperty("disabled", true);
  });

  it("shows the bulk bar for selected rows and hides actions without permission", async () => {
    const archive = vi.fn();
    const exportRows = vi.fn();
    const { container } = render(
      <Harness
        pages={pagesOf({ first: { items: rows(3), next: null } })}
        permissions={["project.view"]}
        bulkActions={[
          { id: "archive", labelKey: "fx.archive", permission: "project.archive", run: archive },
          { id: "export", labelKey: "fx.export", run: exportRows },
        ]}
      />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "Select r0" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Select r1" }));
    const bulk = screen.getByRole("region", { name: "Bulk actions" });
    expect(within(bulk).getByText("2 selected")).toBeTruthy();
    expect(within(bulk).queryByRole("button", { name: "Archive" })).toBeNull();
    await userEvent.click(within(bulk).getByRole("button", { name: "Export" }));
    expect(exportRows.mock.calls[0]?.[0]).toHaveLength(2);
    expect(screen.getAllByRole("row").filter((r) => r.getAttribute("aria-selected") === "true")).toHaveLength(2);
    expect(await axeBlocking(container)).toEqual([]);

    await userEvent.click(screen.getByRole("checkbox", { name: "Select all on this page" }));
    expect(within(screen.getByRole("region", { name: "Bulk actions" })).getByText("3 selected")).toBeTruthy();
  });

  // DESIGN-08: the table scrolls sideways inside its own region, not the page.
  it("wraps the table in a keyboard-focusable scroll region named after the caption", () => {
    render(<Harness pages={pagesOf({ first: { items: rows(1), next: null } })} />);
    const scroll = screen.getByRole("region", { name: "Projects" });
    expect(scroll.getAttribute("tabindex")).toBe("0");
    expect(scroll.className).toContain("aip-register__scroll");
    expect(within(scroll).getByRole("table")).toBeTruthy();
  });

  it("sorts through the header and marks aria-sort", async () => {
    const seen: RegisterQuery[] = [];
    render(<Harness pages={pagesOf({ first: { items: rows(2), next: null } })} seen={seen} />);
    const code = screen.getByRole("columnheader", { name: /Code/ });
    expect(code.getAttribute("aria-sort")).toBe("none");
    await userEvent.click(within(code).getByRole("button"));
    expect(seen.at(-1)?.sort).toEqual({ id: "code", dir: "asc" });
    expect(screen.getByRole("columnheader", { name: /Code/ }).getAttribute("aria-sort")).toBe("ascending");
    await userEvent.click(within(screen.getByRole("columnheader", { name: /Code/ })).getByRole("button"));
    expect(seen.at(-1)?.sort).toEqual({ id: "code", dir: "desc" });
    expect(within(screen.getByRole("columnheader", { name: "Region" })).queryByRole("button")).toBeNull();
  });

  it("moves between rows with the arrow keys and opens with Enter", async () => {
    const open = vi.fn();
    render(<Harness pages={pagesOf({ first: { items: rows(3), next: null } })} onOpenRow={open} />);
    const bodyRows = screen.getAllByRole("row").slice(1);
    act(() => bodyRows[0]!.focus());
    fireEvent.keyDown(bodyRows[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(bodyRows[1]);
    fireEvent.keyDown(bodyRows[1]!, { key: "Enter" });
    expect(open).toHaveBeenCalledWith(expect.objectContaining({ id: "r1" }));
    expect(bodyRows.map((r) => r.tabIndex)).toEqual([-1, 0, -1]);
  });

  it("toggles columns and puts them in the query", async () => {
    const seen: RegisterQuery[] = [];
    render(<Harness pages={pagesOf({ first: { items: rows(1), next: null } })} seen={seen} />);
    await userEvent.click(screen.getByText("Columns", { selector: "summary" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Region" }));
    expect(seen.at(-1)?.columns).toEqual(["code", "name"]);
    expect(screen.queryByRole("columnheader", { name: "Region" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Restore defaults" }));
    expect(seen.at(-1)?.columns).toBeUndefined();
    expect(screen.getByRole("columnheader", { name: "Region" })).toBeTruthy();
  });

  it("links Export CSV to the server endpoint only when one is given", () => {
    const { unmount } = render(<Harness pages={pagesOf({ first: { items: rows(1), next: null } })} />);
    expect(screen.queryByRole("link", { name: "Export CSV" })).toBeNull();
    unmount();
    render(
      <Harness
        pages={pagesOf({ first: { items: rows(1), next: null } })}
        initial={{ filters: { status: ["active"] }, limit: 50 }}
        exportHref={(q) => `/api/v1/projects/export.csv?status=${String(q.filters.status)}`}
      />,
    );
    expect(screen.getByRole("link", { name: "Export CSV" }).getAttribute("href")).toBe(
      "/api/v1/projects/export.csv?status=active",
    );
  });

  it.each([
    ["empty", result({ items: [], nextCursor: null }), "Nothing matches these filters."],
    ["loading", result(undefined, { isPending: true }), "Loading…"],
    ["error", result(undefined, { isError: true }), "The list could not be loaded."],
  ] as const)("has an accessible %s state", async (_name, state, text) => {
    const { container } = render(<Harness pages={() => state} />);
    expect(screen.getAllByText(text).length).toBeGreaterThan(0);
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("retries after an error", async () => {
    const refetch = vi.fn();
    render(<Harness pages={() => result(undefined, { isError: true, refetch })} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("shows the failed request's reference with the error", () => {
    render(<Harness pages={() => result(undefined, { isError: true, requestId: "req-1234" })} />);
    expect(within(screen.getByRole("alert")).getByText(/Reference: req-1234/)).toBeTruthy();
  });

  it("renders the caller's empty state in place of the default text", () => {
    render(<Harness pages={() => result({ items: [], nextCursor: null })} empty={<p>Nothing here yet</p>} />);
    expect(screen.getByText("Nothing here yet")).toBeTruthy();
    expect(screen.queryByText("Nothing matches these filters.")).toBeNull();
  });

  it("renders a populated register without axe violations", async () => {
    const { container } = render(<Harness pages={pagesOf({ first: { items: rows(3), next: "c1" } })} />);
    expect(screen.getByRole("table", { name: "Projects" })).toBeTruthy();
    expect(await axeBlocking(container)).toEqual([]);
    expect(RegisterTable).toBeTypeOf("function");
  });
});
