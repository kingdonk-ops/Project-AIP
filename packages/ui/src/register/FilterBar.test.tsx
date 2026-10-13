import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { FilterBar, SEARCH_DEBOUNCE_MS } from "./FilterBar";
import { filters, t } from "./fixture";
import type { RegisterQuery } from "./types";

afterEach(() => vi.useRealTimers());

describe("FilterBar", () => {
  it("debounces the search by 300 ms and drops the cursor", () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    render(<FilterBar filters={filters} query={{ filters: {}, limit: 50, cursor: "c9" }} onChange={onChange} translate={t} />);
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "ich" } });
    act(() => vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1));
    expect(onChange).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onChange).toHaveBeenCalledWith({ filters: {}, limit: 50, q: "ich" });
  });

  it("changes a quick filter and clears everything", async () => {
    const seen: RegisterQuery[] = [];
    const query: RegisterQuery = { filters: { status: ["draft"] }, q: "x", limit: 50 };
    const { container } = render(<FilterBar filters={filters} query={query} onChange={(q) => seen.push(q)} translate={t} />);
    await userEvent.selectOptions(screen.getByLabelText("Status"), ["active"]);
    expect(seen.at(-1)?.filters.status).toEqual(["active", "draft"]);
    await userEvent.click(screen.getByRole("button", { name: "Clear all" }));
    expect(seen.at(-1)).toEqual({ filters: {}, limit: 50 });
    expect(await axeBlocking(container)).toEqual([]);
  });
});
