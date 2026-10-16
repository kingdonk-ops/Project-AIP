import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { tKey } from "../test/translate";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  OfflineState,
  SyncConflictState,
  errorTermKey,
  requestErrorFrom,
} from "./states";

describe("states", () => {
  it("EmptyState shows its keys and runs its action", async () => {
    const onSelect = vi.fn();
    const { container } = render(
      <EmptyState
        icon="folder"
        titleKey="ncr.empty.title"
        bodyKey="ncr.empty.body"
        action={{ labelKey: "ncr.new", onSelect }}
        translate={tKey}
      />,
    );
    expect(screen.getByText("ncr.empty.title")).toBeTruthy();
    expect(screen.getByText("ncr.empty.body")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "ncr.new" }));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("LoadingState is aria-busy in both variants", async () => {
    const { container, rerender } = render(<LoadingState variant="skeleton" rows={4} translate={tKey} />);
    expect(container.querySelector("[aria-busy=true]")).not.toBeNull();
    expect(container.querySelectorAll(".aip-state__skeleton-row")).toHaveLength(4);
    expect(screen.getByText("ui.loading")).toBeTruthy();
    expect(await axeBlocking(container)).toEqual([]);
    rerender(<LoadingState variant="spinner" translate={tKey} />);
    expect(container.querySelector("[aria-busy=true]")).not.toBeNull();
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("maps HTTP status to a term key", () => {
    expect(errorTermKey(403)).toBe("ui.error.forbidden");
    expect(errorTermKey(404)).toBe("ui.error.notFound");
    expect(errorTermKey(409)).toBe("ui.error.conflict");
    expect(errorTermKey(500)).toBe("ui.error.generic");
    expect(errorTermKey(503)).toBe("ui.error.generic");
    expect(errorTermKey(undefined)).toBe("ui.error.generic");
  });

  it("ErrorState with 409 shows the conflict text and the request id; Retry calls back", async () => {
    const onRetry = vi.fn();
    const { container } = render(
      <ErrorState error={{ status: 409, requestId: "req_123" }} onRetry={onRetry} translate={tKey} />,
    );
    expect(screen.getByText("ui.error.conflict")).toBeTruthy();
    expect(screen.getByText("req_123").tagName).toBe("CODE");
    await userEvent.click(screen.getByRole("button", { name: "ui.error.retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("ErrorState copies the request id", async () => {
    const user = userEvent.setup();
    render(<ErrorState error={{ status: 500, requestId: "req_9" }} onRetry={() => {}} translate={tKey} />);
    await user.click(screen.getByRole("button", { name: "ui.error.copy" }));
    await expect(navigator.clipboard.readText()).resolves.toBe("req_9");
    expect(await screen.findByText("ui.error.copied")).toBeTruthy();
  });

  it("ErrorState without a request id shows no reference", () => {
    render(<ErrorState error={{ status: 404 }} onRetry={() => {}} translate={tKey} />);
    expect(screen.getByText("ui.error.notFound")).toBeTruthy();
    expect(screen.queryByText("ui.error.reference")).toBeNull();
  });

  it("requestErrorFrom reads status and X-Request-Id from a Response", () => {
    const res = new Response(null, { status: 500, headers: { "X-Request-Id": "req_e2e" } });
    expect(requestErrorFrom(res)).toEqual({ status: 500, requestId: "req_e2e" });
    expect(requestErrorFrom(new Response(null, { status: 404 }))).toEqual({ status: 404, requestId: null });
  });

  it("OfflineState shows the offline text and optional retry", async () => {
    const onRetry = vi.fn();
    const { container } = render(<OfflineState onRetry={onRetry} translate={tKey} />);
    expect(screen.getByText("ui.offline.title")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "ui.error.retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("SyncConflictState offers keep mine, keep theirs and merge", async () => {
    const onKeepMine = vi.fn();
    const onKeepTheirs = vi.fn();
    const onMerge = vi.fn();
    const { container, rerender } = render(
      <SyncConflictState
        mine={"A"}
        theirs={"B"}
        onKeepMine={onKeepMine}
        onKeepTheirs={onKeepTheirs}
        onMerge={onMerge}
        translate={tKey}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "ui.conflict.keepMine" }));
    await userEvent.click(screen.getByRole("button", { name: "ui.conflict.keepTheirs" }));
    await userEvent.click(screen.getByRole("button", { name: "ui.conflict.merge" }));
    expect([onKeepMine, onKeepTheirs, onMerge].map((f) => f.mock.calls.length)).toEqual([1, 1, 1]);
    expect(screen.getByRole("region", { name: "ui.conflict.mine" }).textContent).toContain("A");
    expect(await axeBlocking(container)).toEqual([]);
    rerender(
      <SyncConflictState mine={"A"} theirs={"B"} onKeepMine={onKeepMine} onKeepTheirs={onKeepTheirs} translate={tKey} />,
    );
    expect(screen.queryByRole("button", { name: "ui.conflict.merge" })).toBeNull();
  });
});
