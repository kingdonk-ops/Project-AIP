// ASSETS-03: the asset tree and create form against a whole deployment (the compose stack in CI lane
// e2e-skeleton, and the demo after a deploy). A kaefer-demo admin (A) creates a site and a child
// with a Tag Number through /assets/new, sees the child under the site in the tree, and a second
// create with the same Tag Number shows the "already used" message. The tenant-b admin (B) gets the
// not-found page for A's asset and a 404 from the API. A then deletes both assets, so the demo
// tenant does not fill up. Without the fixture credentials (E2E_USER_*/E2E_PASS_*) the suite skips.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { apiCall } from "../fixtures/api";
import { loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;

const run = runId();
const siteName = `E2E-${run} Site`;
const childName = `E2E-${run} Pump`;
const tag = `E2E-${run}-P1`;

async function expectNoSeriousAxe(page: Page, where: string) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
    `${where}: no serious or critical axe violations`,
  ).toEqual([]);
}

interface Created {
  id: string;
  internalTag: string;
  syncVersion: number;
}

async function createThroughForm(page: Page, path: string, name: string, tagNumber?: string): Promise<Created> {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: "Create asset" })).toBeVisible();
  await page.getByLabel("Name (required)").fill(name);
  if (tagNumber) await page.getByLabel("Tag Number").fill(tagNumber);
  const created = page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v1/assets");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const response = await created;
  expect(response.status(), `A creates ${name}`).toBe(201);
  return (await response.json()) as Created;
}

(users ? test.describe : test.describe.skip)("ASSETS-03 asset tree and create form", () => {
  test("@skeleton A builds a site with a tagged child; B cannot open it", async ({ browser }) => {
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    const made: Created[] = [];
    try {
      await loginAs(pageA, users!.a);

      const site = await createThroughForm(pageA, "/assets/new", siteName);
      made.push(site);
      await expect(pageA).toHaveURL(new RegExp(`/assets\\?created=${site.internalTag}$`));
      await expect(pageA.getByText(`Asset ${site.internalTag} was created.`)).toBeVisible();

      const child = await createThroughForm(pageA, `/assets/new?parentId=${site.id}`, childName, tag);
      made.unshift(child); // delete the child first
      await expect(pageA).toHaveURL(new RegExp(`[?&]under=${site.id}(&|$)`));
      await expect(pageA.getByText(`Within: ${siteName}`)).toBeVisible();
      await expect(pageA.locator("tbody tr[data-row]").filter({ hasText: childName })).toHaveCount(1);

      // The child is under the site in the tree.
      const tree = pageA.getByRole("tree", { name: "Asset tree" });
      const siteItem = tree.getByRole("treeitem", { name: siteName });
      await siteItem.focus();
      if ((await siteItem.getAttribute("aria-expanded")) === "false") await pageA.keyboard.press("ArrowRight");
      await expect(siteItem).toHaveAttribute("aria-expanded", "true");
      const group = pageA.locator(`[id="${await siteItem.getAttribute("aria-owns")}"]`);
      const childItem = group.getByRole("treeitem", { name: childName });
      await expect(childItem).toBeVisible();
      await expect(childItem).toHaveAttribute("aria-level", "2");
      await expectNoSeriousAxe(pageA, "assets page");

      // A second create with the same Tag Number is flagged while typing.
      await pageA.goto("/assets/new");
      await pageA.getByLabel("Tag Number").fill(tag.toLowerCase());
      await expect(pageA.getByText(`Already used by ${childName} (${child.internalTag})`)).toBeVisible();
      await expectNoSeriousAxe(pageA, "create form with a taken Tag Number");

      // Cross-tenant: B gets the not-found page and a 404.
      await loginAs(pageB, users!.b);
      await pageB.goto(`/assets/${child.id}/edit`);
      await expect(pageB.getByText("Not found"), "another tenant's asset is not found").toBeVisible();
      const fetched = await apiCall(pageB, "GET", `/api/v1/assets/${child.id}`);
      expect(fetched.status, "RLS: B's fetch of A's asset is 404").toBe(404);
    } finally {
      for (const asset of made) {
        const deleted = await apiCall(pageA, "DELETE", `/api/v1/assets/${asset.id}?syncVersion=${asset.syncVersion}`);
        expect(deleted.status, "A removes the test asset").toBe(204);
      }
      await contextA.close();
      await contextB.close();
    }
  });
});
