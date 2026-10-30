// ITEMTYPES-03: the content types and item types admin pages against a whole deployment (the
// compose stack in CI lane e2e-skeleton). A kaefer-demo admin (A) creates a content type, a
// category and an item type, drafts its attributes as JSON, fixes a server-reported issue and
// publishes version 1; the tenant-b admin (B) can neither open nor fetch A's item type, nor see
// the content type in B's register. Axe runs on the register, the detail page and the editor.
//
// Not tagged @staging (and skipped on that project): published item types cannot be deleted, so
// every run would leave a content type behind in the demo tenant.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { apiCall } from "../fixtures/api";
import { loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;

// Keys allow lower-case letters, digits and underscores only.
const run = runId().replace(/[^a-z0-9]/gi, "_").toLowerCase();
const contentTypeKey = `e2e_${run}`;
const contentTypeName = `E2E ${run}`;

function attributes(unit: string): string {
  return JSON.stringify(
    [
      {
        key: "wall_thickness",
        label: "Wall thickness",
        fieldType: "measurement",
        required: true,
        config: { unit, min: 0, max: 100 },
      },
      {
        key: "material",
        label: "Material",
        fieldType: "dropdown",
        config: {
          options: [
            { value: "cs", label: "Carbon steel" },
            { value: "ss", label: "Stainless" },
          ],
        },
      },
    ],
    null,
    2,
  );
}

async function expectNoSeriousAxe(page: Page, where: string) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
    `${where}: no serious or critical axe violations`,
  ).toEqual([]);
}

function responseFor(page: Page, method: string, path: RegExp) {
  return page.waitForResponse((r) => r.request().method() === method && path.test(new URL(r.url()).pathname));
}

(users ? test.describe : test.describe.skip)("ITEMTYPES-03 content types and item types admin", () => {
  test("@skeleton A builds and publishes an item type; B cannot see it", async ({ browser }, testInfo) => {
    test.skip(testInfo.project.name === "staging", "published item types cannot be deleted from the demo tenant");
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    try {
      await loginAs(pageA, users!.a);

      // Settings nav → the register.
      await pageA.goto("/");
      await pageA.getByRole("link", { name: "Content types", exact: true }).first().click();
      await expect(pageA).toHaveURL(/\/admin\/content-types$/);
      await expect(pageA.getByRole("heading", { level: 1, name: "Content types" })).toBeVisible();

      // Create the content type.
      await pageA.getByRole("button", { name: "Create content type" }).first().click();
      const createDialog = pageA.getByRole("dialog");
      await createDialog.getByLabel("Key", { exact: true }).fill(contentTypeKey);
      await createDialog.getByLabel("Name", { exact: true }).fill(contentTypeName);
      const created = responseFor(pageA, "POST", /^\/api\/v1\/content-types$/);
      await createDialog.getByRole("button", { name: "Create", exact: true }).click();
      expect((await created).status(), "A creates a content type").toBe(201);
      const row = pageA.getByRole("link", { name: contentTypeName });
      await expect(row, "the new content type is in the register").toBeVisible();
      await expectNoSeriousAxe(pageA, "content types register");

      // Detail → Categories → add a category for items.
      await row.click();
      await expect(pageA.getByRole("heading", { level: 1, name: contentTypeName })).toBeVisible();
      await pageA.getByRole("tab", { name: "Categories" }).click();
      await expect(pageA).toHaveURL(/tab=categories/);
      await pageA.getByRole("button", { name: "Add category" }).click();
      const categoryDialog = pageA.getByRole("dialog");
      await categoryDialog.getByLabel("Category key").fill(`piping_${run}`);
      await categoryDialog.getByLabel("Category name").fill(`Piping ${run}`);
      await categoryDialog.getByLabel("Applicable for").selectOption({ label: "Item" });
      const category = responseFor(pageA, "POST", /^\/api\/v1\/item-categories$/);
      await categoryDialog.getByRole("button", { name: "Add category" }).click();
      expect((await category).status(), "A adds a category").toBe(201);
      await expect(pageA.getByRole("cell", { name: `Piping ${run}` })).toBeVisible();
      await expectNoSeriousAxe(pageA, "content type detail (categories)");

      // Item types → add one, then open its editor.
      await pageA.getByRole("tab", { name: "Item types" }).click();
      await pageA.getByRole("button", { name: "Add item type" }).click();
      const itemDialog = pageA.getByRole("dialog");
      await itemDialog.getByLabel("Item type key").fill(`pipe_spool_${run}`);
      await itemDialog.getByLabel("Item type name").fill(`Pipe spool ${run}`);
      const itemCreated = responseFor(pageA, "POST", /^\/api\/v1\/item-types$/);
      await itemDialog.getByRole("button", { name: "Add item type" }).click();
      const itemResponse = await itemCreated;
      expect(itemResponse.status(), "A adds an item type").toBe(201);
      const itemTypeId = ((await itemResponse.json()) as { id: string }).id;
      await pageA.getByRole("link", { name: `Pipe spool ${run}` }).click();
      await expect(pageA.getByRole("heading", { level: 1, name: `Pipe spool ${run}` })).toBeVisible();
      await expect(pageA.getByText("Not published")).toBeVisible();
      const editorUrl = new URL(pageA.url()).pathname;

      // Schema → Create draft → paste with an invalid unit → Save → the issue is listed.
      await pageA.getByRole("tab", { name: "Schema" }).click();
      await pageA.getByRole("button", { name: "Create draft" }).click();
      const editor = pageA.getByLabel("Attributes (JSON)");
      await expect(editor).toBeEditable();
      await editor.fill(attributes("in"));
      const invalid = responseFor(pageA, "PATCH", /\/versions\/[^/]+$/);
      await pageA.getByRole("button", { name: "Save draft" }).click();
      expect((await invalid).status(), "the API rejects the unit").toBe(422);
      const issues = pageA.getByRole("alert").filter({ hasText: "Problems reported by the server" });
      await expect(issues).toContainText("attributes[0].config");
      await expectNoSeriousAxe(pageA, "item type editor (schema with issues)");

      // Fix the unit → Save → the preview lists both attributes.
      await editor.fill(attributes("mm"));
      const saved = responseFor(pageA, "PATCH", /\/versions\/[^/]+$/);
      await pageA.getByRole("button", { name: "Save draft" }).click();
      expect((await saved).status(), "the fixed draft is saved").toBe(200);
      const preview = pageA.getByRole("list", { name: "Preview" });
      await expect(preview.getByText("Wall thickness")).toBeVisible();
      await expect(preview.getByText("Material", { exact: true })).toBeVisible();
      await expect(preview.locator("input, select, textarea"), "the preview renders no inputs").toHaveCount(0);

      // Publish with a summary → Published v1.
      await pageA.getByRole("button", { name: "Publish", exact: true }).click();
      const publishDialog = pageA.getByRole("dialog");
      await publishDialog.getByLabel("Change summary").fill("first");
      const published = responseFor(pageA, "POST", /\/publish$/);
      await publishDialog.getByRole("button", { name: "Publish version" }).click();
      expect((await published).status(), "A publishes version 1").toBe(200);
      await expect(pageA.getByText("Published v1")).toBeVisible();

      // Versions lists v1 with today's date in the viewer's time zone.
      await pageA.getByRole("tab", { name: "Versions" }).click();
      const today = await pageA.evaluate(() => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date()));
      const v1 = pageA.getByRole("row").filter({ has: pageA.getByRole("button", { name: "v1" }) });
      await expect(v1).toContainText(today);
      await expect(v1).toContainText("first");

      // Cross-tenant: B gets the not-found state and a 404, and does not see A's content type.
      await loginAs(pageB, users!.b);
      await pageB.goto(editorUrl);
      await expect(pageB.getByText("Not found"), "ADR 0035: another tenant's item type is not found").toBeVisible();
      const fetched = await apiCall(pageB, "GET", `/api/v1/item-types/${itemTypeId}`);
      expect(fetched.status, "RLS: B's fetch of A's item type is 404").toBe(404);
      const listB = responseFor(pageB, "GET", /^\/api\/v1\/content-types$/);
      await pageB.goto("/admin/content-types");
      expect((await listB).status(), "B reads its own content types").toBe(200);
      await expect(pageB.getByRole("heading", { level: 1, name: "Content types" })).toBeVisible();
      await expect(pageB.getByText(contentTypeName), "B's register does not list A's content type").toHaveCount(0);
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
