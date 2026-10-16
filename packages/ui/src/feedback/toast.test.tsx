import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { tKey } from "../test/translate";
import { MAX_VISIBLE_TOASTS, TOAST_TIMEOUT_MS, Toaster, toast } from "./toast";

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

describe("toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    act(() => toast.clear());
    vi.useRealTimers();
  });

  it("success renders in the polite region and is gone after 5s", () => {
    const { container } = render(<Toaster translate={tKey} />);
    act(() => {
      toast.success("saved");
    });
    expect(container.querySelector("[aria-live=polite]")?.textContent).toContain("saved");
    expect(TOAST_TIMEOUT_MS).toBe(5000);
    advance(4999);
    expect(screen.queryByText("saved")).not.toBeNull();
    advance(1);
    expect(screen.queryByText("saved")).toBeNull();
  });

  it("pauses while hovered: hover at 4s, leave at 8s, dismissed at 13s", () => {
    render(<Toaster translate={tKey} />);
    act(() => {
      toast.info("synced");
    });
    advance(4000);
    fireEvent.mouseEnter(screen.getByText("synced"));
    advance(4000);
    fireEvent.mouseLeave(screen.getByText("synced"));
    advance(4999);
    expect(screen.queryByText("synced")).not.toBeNull();
    advance(1);
    expect(screen.queryByText("synced")).toBeNull();
  });

  it("pauses while focused", () => {
    render(<Toaster translate={tKey} />);
    act(() => {
      toast.success("saved", undefined, { action: { labelKey: "undo", onSelect: () => {} } });
    });
    fireEvent.focus(screen.getByRole("button", { name: "undo" }));
    advance(10_000);
    expect(screen.queryByText("saved")).not.toBeNull();
  });

  it("shows at most 3 at a time", () => {
    render(<Toaster translate={tKey} />);
    act(() => {
      for (let i = 1; i <= 5; i++) toast.info("toast.n", { n: i });
    });
    expect(MAX_VISIBLE_TOASTS).toBe(3);
    expect(screen.getAllByText(/^toast\.n/)).toHaveLength(3);
  });

  it("errors are assertive and stay until dismissed", () => {
    const { container } = render(<Toaster translate={tKey} />);
    act(() => {
      toast.error("failed", { code: 7 });
    });
    expect(container.querySelector("[aria-live=assertive]")?.textContent).toContain("failed{code=7}");
    advance(60_000);
    expect(screen.queryByText("failed{code=7}")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "ui.toast.dismiss" }));
    expect(screen.queryByText("failed{code=7}")).toBeNull();
  });

  it("runs the action and dismisses the toast", () => {
    const onSelect = vi.fn();
    render(<Toaster translate={tKey} />);
    act(() => {
      toast.error("failed", undefined, { action: { labelKey: "retry", onSelect } });
    });
    fireEvent.click(screen.getByRole("button", { name: "retry" }));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(screen.queryByText("failed")).toBeNull();
  });

  it("dismiss(id) removes one toast", () => {
    render(<Toaster translate={tKey} />);
    let id = 0;
    act(() => {
      id = toast.error("one");
      toast.error("two");
    });
    act(() => toast.dismiss(id));
    expect(screen.queryByText("one")).toBeNull();
    expect(screen.queryByText("two")).not.toBeNull();
  });

  it("Toaster with 2 toasts has no serious or critical axe violations", async () => {
    vi.useRealTimers();
    const { container } = render(<Toaster translate={tKey} />);
    act(() => {
      toast.success("saved");
      toast.error("failed");
    });
    expect(await axeBlocking(container)).toEqual([]);
  });
});
