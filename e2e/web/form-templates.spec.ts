// FORMS-04: the form template register and detail pages against a whole deployment (the compose
// stack in CI lane e2e-skeleton). A kaefer-demo admin uploads a template whose JSON the server
// refuses, fixes it, publishes v1, starts and publishes v2, and compares the two; a tenant-b user
// gets the not-found state for that template and does not see it in the register. Axe runs on
// every page state.
//
// Not tagged @staging: published revisions cannot be deleted, so every run would add a template to
// the demo tenant. Without the fixture credentials (E2E_USER_*/E2E_PASS_*) the suite skips.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;

const V1 = {
  schemaVersion: 1,
  sections: [
    {
      key: "prep",
      label: "Preparation",
      fields: [
        { key: "surface_prepared", type: "boolean", label: "Surface prepared" },
        { key: "dft_avg", type: "measurement", label: "Average DFT", unit: "mm" },
      ],
    },
    { key: "final", label: "Final", fields: [{ key: "remarks", type: "text", label: "Remarks" }] },
  ],
};

// v2: dft_avg becomes required (changed), blast_standard is added, surface_prepared moves section.
const V2 = {
  schemaVersion: 1,
  sections: [
    {
      key: "prep",
      label: "Preparation",
      fields: [
        { key: "dft_avg", type: "measurement", label: "Average DFT", unit: "mm", required: true },
        {
          key: "blast_standard",
          type: "dropdown",
          label: "Blast standard",
          options: [{ value: "sa2_5", label: "Sa 2.5" }],
        },
      ],
    },
    {
      key: "final",
      label: "Final",
      fields: [
        { key: "remarks", type: "text", label: "Remarks" },
        { key: "surface_prepared", type: "boolean", label: "Surface prepared" },
      ],
    },
  ],
};

// v1 with a field type the registry does not have.
const BROKEN = structuredClone(V1);
(BROKEN.sections[1]!.fields[0] as Record<string, unknown>).type = "barcode";

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

function toast(page: Page, text: string) {
  return page.locator("[aria-live=polite], [aria-live=assertive]").getByText(text);
}

async function confirmAction(page: Page, title: string, button: string) {
  const dialog = page.getByRole("dialog", { name: title });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: button }).click();
  await expect(dialog).toBeHidden();
}

(users ? test.describe : test.describe.skip)("FORMS-04 form template pages", () => {
  test("@skeleton tenant A uploads, publishes and compares revisions; tenant B cannot see the template", async ({
    browser,
  }) => {
    const u = users!;
    const code = `e2e-tpl-${runId()}`.slice(0, 63);
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    try {
      await loginAs(pageA, u.a);

      // The register.
      await pageA.goto("/templates");
      await expect(pageA.getByRole("heading", { level: 1, name: "Form templates" })).toBeVisible();
      await expectNoBlockingAxe(pageA);

      // Upload a template the server refuses: the issue is listed and the text is kept.
      await pageA.getByRole("button", { name: "Upload template" }).first().click();
      const upload = pageA.getByRole("dialog", { name: "Upload template" });
      await expect(upload).toBeVisible();
      await upload.getByRole("textbox", { name: "Code" }).fill(code);
      await upload.getByRole("textbox", { name: "Name" }).fill("Coating ITR (e2e)");
      await upload.getByRole("combobox", { name: "Kind" }).selectOption("inspection");
      const json = upload.getByRole("textbox", { name: "Template JSON" });
      await json.fill(JSON.stringify(BROKEN, null, 2));
      await upload.getByRole("button", { name: "Upload", exact: true }).click();
      await expect(upload.getByText("This field type is not in the registry.")).toBeVisible();
      await expect(upload.getByText(/^sections\[1\]\.fields\[0\]/)).toBeVisible();
      await expectNoBlockingAxe(pageA);

      // Fix it and upload: the detail page opens on draft v1.
      await json.fill(JSON.stringify(V1, null, 2));
      await upload.getByRole("button", { name: "Upload", exact: true }).click();
      await expect(pageA).toHaveURL(/\/templates\/[0-9a-f-]{36}/);
      const templateUrl = new URL(pageA.url()).pathname;
      await expect(pageA.getByRole("heading", { level: 1, name: "Coating ITR (e2e)" })).toBeVisible();
      await expect(pageA.getByRole("heading", { name: "Revision v1" })).toBeVisible();

      // Publish v1.
      await pageA.getByRole("button", { name: "Publish v1" }).click();
      await confirmAction(pageA, `Publish v1 of ${code}?`, "Publish");
      await expect(toast(pageA, `v1 of ${code} was published.`)).toBeVisible();

      // Start v2 from new JSON and publish it.
      await pageA.getByRole("button", { name: "New draft" }).click();
      const draft = pageA.getByRole("dialog", { name: `New draft of ${code}` });
      await draft.getByRole("textbox", { name: "Template JSON" }).fill(JSON.stringify(V2, null, 2));
      await draft.getByRole("button", { name: "Save draft" }).click();
      await expect(toast(pageA, "Draft v2 was created.")).toBeVisible();
      await pageA.getByRole("button", { name: "Publish v2" }).click();
      await confirmAction(pageA, `Publish v2 of ${code}?`, "Publish");
      await expect(toast(pageA, `v2 of ${code} was published.`)).toBeVisible();
      await expect(pageA.getByRole("table", { name: "Revision history" }).getByText("Superseded")).toBeVisible();
      await expectNoBlockingAxe(pageA);

      // Compare v1 with v2.
      await pageA.getByRole("tab", { name: "Compare" }).click();
      await expect(pageA.getByRole("combobox", { name: "From" })).toHaveValue("1");
      await expect(pageA.getByRole("combobox", { name: "To" })).toHaveValue("2");
      await expect(pageA.getByText("1 added, 0 removed, 1 changed, 1 moved")).toBeVisible();
      await expect(pageA.getByText("Moved from section prep to final")).toBeVisible();
      await expect(pageA).toHaveURL(/tab=compare/);
      await expectNoBlockingAxe(pageA);

      // Tenant B: A's template is not found, and B's register does not list it.
      await loginAs(pageB, u.b);
      await pageB.goto(templateUrl);
      await expect(pageB.getByText("Not found")).toBeVisible();
      await expectNoBlockingAxe(pageB);
      await pageB.goto(`/templates?q=${encodeURIComponent(code)}`);
      await expect(pageB.getByRole("heading", { level: 1, name: "Form templates" })).toBeVisible();
      await expect(pageB.getByText("No templates match these filters.")).toBeVisible();
      await expect(pageB.getByRole("link", { name: code })).toHaveCount(0);
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
