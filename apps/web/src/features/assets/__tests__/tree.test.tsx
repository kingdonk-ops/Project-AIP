import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AssetTree, EXPANDED_STORAGE_KEY } from "../AssetTree";
import { asset, assetsApi, blocking, resolveRelativeFetch, restoreFetch, server } from "./helpers";

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
beforeEach(() => window.sessionStorage.clear());
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

const siteA = asset({ name: "Site A", childCount: 2 });
const siteB = asset({ name: "Site B" });
const unit1 = asset({ name: "Unit 1", parentId: siteA.id, childCount: 0 });
const unit2 = asset({ name: "Unit 2", parentId: siteA.id, childCount: 0 });
const ALL = [siteA, siteB, unit1, unit2];

function renderTree(onSelect = vi.fn(), selectedId?: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <AssetTree selectedId={selectedId} onSelect={onSelect} />
    </QueryClientProvider>,
  );
  return { ...view, onSelect };
}

const item = (name: string) => screen.getByRole("treeitem", { name });

function tabStops(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll<HTMLElement>('[role="treeitem"][tabindex="0"]')).map((el) => el.dataset.id ?? "");
}

describe("asset tree", () => {
  it("is operable with the keyboard alone and keeps one roving tab stop", async () => {
    const seen: URL[] = [];
    server.use(...assetsApi(ALL, seen));
    const user = userEvent.setup();
    const { container, onSelect } = renderTree();

    const site = await screen.findByRole("treeitem", { name: "Site A" });
    expect(seen[0]?.searchParams.get("parentId")).toBe("root");
    expect(seen[0]?.searchParams.get("sort")).toBe("position");
    expect(site.getAttribute("aria-level")).toBe("1");
    expect(site.getAttribute("aria-expanded")).toBe("false");
    expect(item("Site B").hasAttribute("aria-expanded")).toBe(false); // no children
    expect(tabStops(container)).toEqual([siteA.id]);

    await user.tab();
    expect(document.activeElement).toBe(site);

    await user.keyboard("{ArrowRight}");
    await screen.findByRole("treeitem", { name: "Unit 1" });
    expect(site.getAttribute("aria-expanded")).toBe("true");
    expect(seen.some((u) => u.searchParams.get("parentId") === siteA.id)).toBe(true);
    const group = document.getElementById(site.getAttribute("aria-owns") ?? "")!;
    expect(group.getAttribute("role")).toBe("group");
    const children = within(group).getAllByRole("treeitem");
    expect(children.map((c) => c.getAttribute("aria-setsize"))).toEqual(["2", "2"]);
    expect(children.map((c) => c.getAttribute("aria-posinset"))).toEqual(["1", "2"]);
    expect(children[0]!.getAttribute("aria-level")).toBe("2");

    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(item("Unit 1"));
    expect(tabStops(container)).toEqual([unit1.id]);

    await user.keyboard("{ArrowLeft}");
    expect(document.activeElement).toBe(site);
    expect(tabStops(container)).toEqual([siteA.id]);

    await user.keyboard("{End}");
    expect(document.activeElement).toBe(item("Site B"));
    await user.keyboard("{Home}");
    expect(document.activeElement).toBe(site);
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(item("Unit 1")); // Right on an open node enters it
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onSelect).toHaveBeenCalledWith({ id: unit2.id, name: "Unit 2" });

    await user.keyboard("{ArrowLeft}{ArrowLeft}"); // to Site A, then collapse
    expect(site.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("treeitem", { name: "Unit 1" })).toBeNull();
    expect(await blocking(container)).toEqual([]);
  });

  it("remembers expanded nodes for the tab in sessionStorage", async () => {
    server.use(...assetsApi(ALL));
    const first = renderTree();
    await userEvent.click(await screen.findByRole("treeitem", { name: "Site A" }));
    await userEvent.keyboard("{ArrowRight}");
    await screen.findByRole("treeitem", { name: "Unit 1" });
    expect(JSON.parse(window.sessionStorage.getItem(EXPANDED_STORAGE_KEY) ?? "[]")).toEqual([siteA.id]);
    first.unmount();

    renderTree();
    await screen.findByRole("treeitem", { name: "Unit 2" });
  });

  it("marks the selected node and still renders when storage throws", async () => {
    server.use(...assetsApi(ALL));
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    try {
      renderTree(vi.fn(), siteB.id);
      const selected = await screen.findByRole("treeitem", { name: "Site B" });
      expect(selected.getAttribute("aria-selected")).toBe("true");
      expect(item("Site A").getAttribute("aria-selected")).toBe("false");
    } finally {
      spy.mockRestore();
    }
  });

  it("selects a node with a click", async () => {
    server.use(...assetsApi(ALL));
    const { onSelect } = renderTree();
    await userEvent.click(await screen.findByText("Site B"));
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith({ id: siteB.id, name: "Site B" }));
  });
});
