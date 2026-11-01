// ASSETS-03: the asset tree and register (/assets) in the stub lane. The stub session (Vite dev
// server) holds asset.view/create/update/move; the list and get APIs are answered by page.route with
// a fake that honours `parentId`, `under` and `sort=name|-name`. The server's filters, sort, paging
// and CSV export are proven against Postgres in apps/api (test_assets_db.py, test_assets_export_db.py);
// creating assets and the cross-tenant check need real sessions (assets-live.spec.ts).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

async function expectNoBlockingAxe(page: Page, where: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking, `${where}: no serious or critical axe violations`).toEqual([]);
}

interface Row {
  id: string;
  name: string;
  parentId: string | null;
  tagNumber: string | null;
}

const ids = (n: number) => `00000000-0000-7000-8000-${String(n).padStart(12, "0")}`;
const ROWS: Row[] = [
  { id: ids(1), name: "Site A", parentId: null, tagNumber: null },
  { id: ids(2), name: "Site B", parentId: null, tagNumber: null },
  { id: ids(3), name: "Unit 1", parentId: ids(1), tagNumber: null },
  { id: ids(4), name: "Unit 2", parentId: ids(1), tagNumber: null },
  { id: ids(5), name: "P-101 feed pump", parentId: ids(3), tagNumber: "P-101" },
  { id: ids(6), name: "P-102 spare pump", parentId: ids(3), tagNumber: "P-102" },
];

function out(row: Row) {
  return {
    ...row,
    path: row.id.replace(/-/g, ""),
    internalTag: `AT-0000-0000-${row.id.slice(-4)}`,
    sortOrder: 0,
    itemTypeId: null,
    itemTypeVersionId: null,
    attributes: {},
    createdBy: null,
    syncVersion: 1,
    createdAt: "2026-10-28T00:00:00Z",
    updatedAt: "2026-10-28T01:00:00Z",
    childCount: ROWS.filter((r) => r.parentId === row.id).length,
  };
}

function subtree(rootId: string): Row[] {
  const children = ROWS.filter((r) => r.parentId === rootId);
  return children.flatMap((c) => [c, ...subtree(c.id)]);
}

function ancestors(row: Row) {
  const chain = [];
  for (let p = row.parentId; p; ) {
    const parent = ROWS.find((r) => r.id === p)!;
    chain.unshift({ id: parent.id, name: parent.name, internalTag: out(parent).internalTag, tagNumber: parent.tagNumber });
    p = parent.parentId;
  }
  return chain;
}

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });

/** Answer the assets and item-types APIs like the server would, from ROWS. */
async function serveAssets(page: Page) {
  await page.route(
    (url) => url.pathname.startsWith("/api/v1/assets"),
    (route) => {
      const url = new URL(route.request().url());
      const tail = url.pathname.slice("/api/v1/assets".length);
      if (tail.startsWith("/")) {
        const row = ROWS.find((r) => r.id === tail.slice(1));
        return route.fulfill(row ? json({ ...out(row), ancestors: ancestors(row) }) : json({ code: "NOT_FOUND" }, 404));
      }
      const params = url.searchParams;
      const parentId = params.get("parentId");
      const under = params.get("under");
      let rows = under ? subtree(under) : [...ROWS];
      if (parentId === "root") rows = rows.filter((r) => r.parentId === null);
      else if (parentId) rows = rows.filter((r) => r.parentId === parentId);
      const sort = params.get("sort") ?? "name";
      if (sort !== "position") rows.sort((a, b) => a.name.localeCompare(b.name) * (sort === "-name" ? -1 : 1));
      return route.fulfill(
        json({ items: rows.map((r) => ({ ...out(r), ancestorNames: ancestors(r).map((a) => a.name) })), nextCursor: null }),
      );
    },
  );
  await page.route(
    (url) => url.pathname.startsWith("/api/v1/item-types"),
    (route) => route.fulfill(json({ items: [] })),
  );
}

async function openAssets(browser: Browser, path: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signInAsStub(page, "alice@kaefer.test");
  await serveAssets(page);
  await page.goto(path);
  return page;
}

const dataRows = (page: Page) => page.locator("tbody tr[data-row]");

/** The tree: inline beside the register, or in the drawer on narrow screens. */
async function openTree(page: Page) {
  const browse = page.getByRole("button", { name: "Browse tree" });
  if (await browse.isVisible()) await browse.click();
  const tree = page.getByRole("tree", { name: "Asset tree" });
  await expect(tree).toBeVisible();
  return tree;
}

test("browse the tree with the keyboard; the URL alone reproduces the scoped, sorted register", async ({ browser }) => {
  const page = await openAssets(browser, "/assets");
  await expect(page.getByRole("heading", { name: "Assets", level: 1 })).toBeVisible();
  await expect(dataRows(page)).toHaveCount(6);

  const tree = await openTree(page);
  const site = tree.getByRole("treeitem", { name: "Site A" });
  await site.focus();
  await page.keyboard.press("ArrowRight");
  await expect(site).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("ArrowDown");
  await expect(tree.getByRole("treeitem", { name: "Unit 1" })).toBeFocused();
  await expectNoBlockingAxe(page, "asset tree (inline, or the drawer on narrow screens)");
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(new RegExp(`[?&]under=${ids(3)}(&|$)`));
  await expect(page.getByText("Within: Unit 1")).toBeVisible();
  await expect(dataRows(page)).toHaveCount(2);
  await expectNoBlockingAxe(page, "assets register within Unit 1");

  await page.getByRole("button", { name: "Show all assets" }).click();
  await expect(page).toHaveURL(/\/assets$/);
  await expect(dataRows(page)).toHaveCount(6);

  // Back into Unit 1, then sort by Name descending.
  const again = await openTree(page);
  await again.getByRole("treeitem", { name: "Unit 1" }).click();
  await expect(dataRows(page)).toHaveCount(2);
  const sortByName = page.getByRole("button", { name: /^Name/ });
  await sortByName.click();
  await expect(page).toHaveURL(/[?&]sort=name(&|$)/);
  await sortByName.click();
  await expect(page).toHaveURL(/[?&]sort=-name(&|$)/);
  await expect(dataRows(page).first()).toContainText("P-102 spare pump");

  const copied = await openAssets(browser, page.url());
  await expect(copied.getByText("Within: Unit 1")).toBeVisible();
  await expect(dataRows(copied)).toHaveCount(2);
  await expect(dataRows(copied).first()).toContainText("P-102 spare pump");
  await expect(copied.getByRole("columnheader", { name: /^Name/ })).toHaveAttribute("aria-sort", "descending");
  const exportHref = await copied.getByRole("link", { name: "Export CSV" }).getAttribute("href");
  const exportUrl = new URL(exportHref ?? "", "http://x");
  expect(exportUrl.pathname).toBe("/api/v1/assets/export.csv");
  expect(exportUrl.searchParams.get("under")).toBe(ids(3));
  expect(exportUrl.searchParams.get("sort")).toBe("-name");
});

test("the move dialog offers the parent picker and passes axe", async ({ browser }) => {
  const page = await openAssets(browser, `/assets?under=${ids(3)}`);
  await expect(dataRows(page)).toHaveCount(2);
  await page.getByRole("button", { name: "Move P-101 feed pump" }).click();
  const dialog = page.getByRole("dialog", { name: "Move P-101 feed pump" });
  await expect(dialog).toBeVisible();
  const picker = dialog.getByRole("combobox", { name: "New parent" });
  await expect(picker).toHaveValue("Site A > Unit 1");
  await picker.click();
  // The moving asset is never offered as its own parent; top level is.
  await expect(dialog.getByRole("option", { name: "Move to top level" })).toBeVisible();
  await expect(dialog.getByRole("option", { name: /P-101 feed pump/ })).toHaveCount(0);
  await expectNoBlockingAxe(page, "move dialog");
});

test("the create form offers the parent picked in the tree and passes axe", async ({ browser }) => {
  const page = await openAssets(browser, `/assets?under=${ids(1)}`);
  await page.getByRole("link", { name: "Create asset" }).first().click();
  await expect(page).toHaveURL(new RegExp(`/assets/new\\?parentId=${ids(1)}$`));
  await expect(page.getByRole("heading", { name: "Create asset", level: 1 })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Parent" })).toHaveValue("Site A");
  await expectNoBlockingAxe(page, "create asset form");
});
