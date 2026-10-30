import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { assetsIndexRoute } from "../../../routes/_app/assets/index";
import { validateAssetsSearch } from "../search";
import { asset, assetsApi, blocking, itemType, itemTypesApi, renderAt, resolveRelativeFetch, restoreFetch, server } from "./helpers";

const VIEW = ["asset.view", "item_type.view"];
const EDIT = [...VIEW, "asset.update", "asset.create"];
const ALL_ACTIONS = [...EDIT, "asset.move"];

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

const pump = itemType({ name: "Pump" });
const siteA = asset({ name: "Site A", childCount: 1 });
const unit1 = asset({ name: "Unit 1", parentId: siteA.id, childCount: 2 });
const p101 = asset({ name: "P-101 feed pump", parentId: unit1.id, tagNumber: "P-101", itemTypeId: pump.id });
const p102 = asset({ name: "P-102 spare", parentId: unit1.id, tagNumber: "P-102" });
const ALL = [siteA, unit1, p101, p102];

const dataRows = () => within(screen.getByRole("table")).getAllByRole("row").slice(1);

describe("assets register", () => {
  it("validateSearch keeps the register query and a valid under, and drops the rest", () => {
    const validate = assetsIndexRoute.options.validateSearch as (s: Record<string, unknown>) => unknown;
    expect(validate({ under: unit1.id, sort: "-name", junk: "x" })).toEqual({ under: unit1.id, sort: "-name" });
    expect(validateAssetsSearch({ under: "not-a-uuid", sort: "-internalTag", limit: "25" })).toEqual({ limit: "25" });
    expect(validateAssetsSearch({ created: "AT-0000-0000-0001", cols: "name,nope,parent" })).toEqual({
      created: "AT-0000-0000-0001",
      cols: "name,parent",
    });
    expect(validateAssetsSearch({ created: "<b>x</b>", itemType: `${pump.id},${pump.id}` })).toEqual({ itemType: pump.id });
  });

  it("shows item type and parent breadcrumb, and only the actions the user holds", async () => {
    server.use(...assetsApi(ALL), ...itemTypesApi([pump]));
    const { container } = renderAt(`/assets?under=${unit1.id}`, EDIT);

    await screen.findByText("P-101 feed pump");
    expect(dataRows()).toHaveLength(2);
    const row = dataRows().find((r) => within(r).queryByText("P-101 feed pump"))!;
    expect(within(row).getByText("Pump")).toBeTruthy();
    await within(row).findByText("Site A > Unit 1");
    expect(within(row).getByRole("link", { name: "Edit P-101 feed pump" }).getAttribute("href")).toBe(`/assets/${p101.id}/edit`);
    expect(within(row).getByRole("link", { name: "Add child to P-101 feed pump" }).getAttribute("href")).toBe(
      `/assets/new?parentId=${p101.id}`,
    );
    expect(screen.queryByRole("button", { name: /^Move/ })).toBeNull(); // no asset.move
    expect(await blocking(container)).toEqual([]);
  });

  it("a viewer sees no row actions and no Create asset", async () => {
    server.use(...assetsApi(ALL), ...itemTypesApi([pump]));
    renderAt(`/assets?under=${unit1.id}`, VIEW);
    await screen.findByText("P-101 feed pump");
    expect(screen.queryByRole("link", { name: /^Edit / })).toBeNull();
    expect(screen.queryByRole("link", { name: "Create asset" })).toBeNull();
  });

  it("the export link carries the tree scope and the sort", async () => {
    server.use(...assetsApi(ALL), ...itemTypesApi([pump]));
    renderAt(`/assets?under=${unit1.id}&sort=-name&itemType=${pump.id}`, ALL_ACTIONS);
    await screen.findByRole("table");
    const href = screen.getByRole("link", { name: "Export CSV" }).getAttribute("href") ?? "";
    const params = new URL(href, window.location.origin).searchParams;
    expect(new URL(href, window.location.origin).pathname).toBe("/api/v1/assets/export.csv");
    expect(params.get("under")).toBe(unit1.id);
    expect(params.get("sort")).toBe("-name");
    expect(params.getAll("itemTypeId")).toEqual([pump.id]);
  });

  it("selecting a tree node narrows the register; the chip clears it in one click", async () => {
    const seen: URL[] = [];
    server.use(...assetsApi(ALL, seen), ...itemTypesApi([pump]));
    const user = userEvent.setup();
    const { router } = renderAt("/assets", ALL_ACTIONS);
    await screen.findByRole("table");
    await waitFor(() => expect(dataRows()).toHaveLength(4));

    const tree = screen.getByRole("tree", { name: "Asset tree" });
    await user.click(within(tree).getByRole("treeitem", { name: "Site A" }));
    await user.keyboard("{ArrowRight}");
    await user.click(await within(tree).findByRole("treeitem", { name: "Unit 1" }));

    await waitFor(() => expect(router.state.location.search).toEqual({ under: unit1.id }));
    await screen.findByText("Within: Unit 1");
    await waitFor(() => expect(dataRows()).toHaveLength(2));
    expect(seen.some((u) => u.searchParams.get("under") === unit1.id)).toBe(true);
    expect(within(tree).getByRole("treeitem", { name: "Unit 1" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("link", { name: "Create asset" }).getAttribute("href")).toBe(`/assets/new?parentId=${unit1.id}`);

    await user.click(screen.getByRole("button", { name: "Show all assets" }));
    await waitFor(() => expect(router.state.location.search).toEqual({}));
    await waitFor(() => expect(dataRows()).toHaveLength(4));
  });

  it("opens the move dialog with the parent picker", async () => {
    server.use(...assetsApi(ALL), ...itemTypesApi([pump]));
    renderAt(`/assets?under=${unit1.id}`, ALL_ACTIONS);
    await userEvent.click(await screen.findByRole("button", { name: "Move P-102 spare" }));
    const dialog = await screen.findByRole("dialog", { name: "Move P-102 spare" });
    expect(within(dialog).getByRole("combobox", { name: "New parent" })).toBeTruthy();
    expect(await blocking(dialog)).toEqual([]);
  });
});
