// FORMS-11: the form designer against a whole deployment (the compose stack in CI lane
// e2e-skeleton). A kaefer-demo admin starts a template in the designer, builds it without writing
// JSON (a second section, a measurement with a unit and a minimum, a dropdown with three options, a
// required yes/no), moves a field with the keyboard, previews it at phone width, sees and fixes a
// lint issue, saves and publishes v1; the template page lists the fields in the designed order. A
// tenant-b user gets the not-found state on A's designer URL. Axe runs on each view.
//
// The measurement uses `mm` with a minimum of 0.25: the server lint accepts only the units of
// TERMS-03's unit contract (mm, in, bar, psi, degC, degF), so `um` would be an UNKNOWN_UNIT.
//
// Not tagged @staging (as FORMS-04): published revisions cannot be deleted, so every run would add a
// template to the demo tenant. Without the fixture credentials (E2E_USER_*/E2E_PASS_*) it skips.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

function toast(page: Page, text: string) {
  return page.locator("[aria-live=polite], [aria-live=assertive]").getByText(text);
}

function canvasRow(page: Page, key: string) {
  return page.getByTestId("designer-canvas").locator(`[data-select="${key}"]`);
}

async function fieldOrder(page: Page, section: string): Promise<string[]> {
  return page
    .getByTestId("designer-canvas")
    .locator(`[data-section="${section}"] [data-field]`)
    .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-field") ?? ""));
}

async function addFromPalette(page: Page, item: string, label: string) {
  await page.getByTestId("designer-palette").getByRole("button", { name: item, exact: true }).click();
  const label_ = page.getByTestId("designer-properties").getByRole("textbox", { name: "Label", exact: true });
  await label_.fill(label);
}

(users ? test.describe : test.describe.skip)("FORMS-11 form designer", () => {
  test("@skeleton tenant A designs and publishes a template without JSON; tenant B cannot open it", async ({ browser }) => {
    const u = users!;
    const code = `e2e-dsg-${runId()}`.slice(0, 63);
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    try {
      await loginAs(pageA, u.a);

      // Start in the designer: code, name and kind only.
      await pageA.goto("/templates");
      await pageA.getByRole("button", { name: "Upload template" }).first().click();
      const upload = pageA.getByRole("dialog", { name: "Upload template" });
      await upload.getByRole("textbox", { name: "Code" }).fill(code);
      await upload.getByRole("textbox", { name: "Name" }).fill("Coating check (designer e2e)");
      await upload.getByRole("button", { name: "Start in designer" }).click();
      await expect(pageA).toHaveURL(/\/templates\/[0-9a-f-]{36}\/revisions\/1\/design$/);
      const designerUrl = new URL(pageA.url()).pathname;
      await expect(canvasRow(pageA, "field_1")).toBeVisible();
      const properties = pageA.getByTestId("designer-properties");

      // A second section whose key follows its label.
      await addFromPalette(pageA, "Section", "Final");
      await expect(canvasRow(pageA, "final")).toBeVisible();

      // The empty section is a lint issue until it has a field.
      const lint = pageA.getByTestId("designer-lint");
      await expect(lint.getByRole("status")).toHaveAttribute("data-lint-status", "issues", { timeout: 15_000 });
      await expect(lint.getByText("The template does not match the form schema.").first()).toBeVisible();

      // Section 1: a measurement, a dropdown and a required yes/no, each after the selected field.
      await canvasRow(pageA, "field_1").click();
      await addFromPalette(pageA, "Measurement", "DFT average");
      await properties.getByRole("combobox", { name: "Unit" }).selectOption("mm");
      await properties.getByRole("textbox", { name: "Minimum" }).fill("0.25");

      await addFromPalette(pageA, "Dropdown", "Blast standard");
      await properties.getByRole("textbox", { name: "Option 1 label" }).fill("Sa 2");
      await properties.getByRole("button", { name: "Add option" }).click();
      await properties.getByRole("textbox", { name: "Option 2 label" }).fill("Sa 2.5");
      await properties.getByRole("button", { name: "Add option" }).click();
      await properties.getByRole("textbox", { name: "Option 3 label" }).fill("Sa 3");
      await expect(properties.getByRole("textbox", { name: "Option 2 value" })).toHaveValue("sa_2_5");

      await addFromPalette(pageA, "Yes/No", "Surface prepared");
      await properties.getByRole("checkbox", { name: "Required" }).check();
      expect(await fieldOrder(pageA, "section_1")).toEqual(["field_1", "dft_average", "blast_standard", "surface_prepared"]);

      // Move "Surface prepared" up with the keyboard.
      await canvasRow(pageA, "surface_prepared").focus();
      await pageA.keyboard.press("Alt+ArrowUp");
      expect(await fieldOrder(pageA, "section_1")).toEqual(["field_1", "dft_average", "surface_prepared", "blast_standard"]);
      await expect(canvasRow(pageA, "surface_prepared")).toBeFocused();

      // Fix the lint issue: give "Final" a field.
      await pageA
        .getByTestId("designer-canvas")
        .locator('[data-section="final"]')
        .getByRole("button", { name: "Add a field" })
        .click();
      await properties.getByRole("textbox", { name: "Label", exact: true }).fill("Remarks");
      await expect(lint.getByText("No issues")).toBeVisible({ timeout: 15_000 });
      await expectNoBlockingAxe(pageA);

      // Preview at phone width: the fields show and the minimum is checked.
      await pageA.getByRole("button", { name: "Preview", exact: true }).click();
      await pageA.getByRole("button", { name: "Phone" }).click();
      const frame = pageA.getByTestId("designer-preview-frame");
      await expect(frame).toHaveAttribute("data-width", "phone");
      expect((await frame.boundingBox())!.width).toBeLessThanOrEqual(375);
      await expect(frame.getByText("Blast standard")).toBeVisible();
      await expect(frame.getByText("Surface prepared")).toBeVisible();
      const dft = frame.getByRole("textbox", { name: /DFT average/ });
      await dft.fill("0.2");
      await dft.blur();
      await expect(frame.getByText("Must be at least 0.25.")).toBeVisible();
      await expectNoBlockingAxe(pageA);

      // Save, then publish v1.
      await pageA.getByRole("button", { name: "Design", exact: true }).click();
      await pageA.getByRole("button", { name: "Save draft" }).click();
      await expect(pageA.getByText("All changes saved")).toBeVisible();
      await expect(lint.getByText("No issues")).toBeVisible({ timeout: 15_000 });
      const publish = pageA.getByRole("button", { name: "Publish v1" });
      await expect(publish).toBeEnabled();
      await publish.click();
      const confirmDialog = pageA.getByRole("dialog", { name: `Publish v1 of ${code}?` });
      await confirmDialog.getByRole("button", { name: "Publish" }).click();
      await expect(toast(pageA, `v1 of ${code} was published.`)).toBeVisible();

      // The template page: v1 published, the outline in the designed order.
      await expect(pageA).toHaveURL(/\/templates\/[0-9a-f-]{36}(\?|$)/);
      await expect(pageA.getByRole("table", { name: "Revision history" }).locator("tbody").getByText("Published", { exact: true })).toBeVisible();
      const outline = pageA.getByRole("table", { name: "Fields in Section 1" });
      await expect(outline).toBeVisible();
      const keys = await outline.locator("tbody tr").evaluateAll((rows) => rows.map((row) => row.textContent ?? ""));
      const order = ["field_1", "dft_average", "surface_prepared", "blast_standard"].map((key) =>
        keys.findIndex((text) => text.includes(key)),
      );
      expect(order).toEqual([0, 1, 2, 3]);

      // Tenant B: A's designer is not found.
      await loginAs(pageB, u.b);
      await pageB.goto(designerUrl);
      await expect(pageB.getByText("Not found")).toBeVisible();
      await expectNoBlockingAxe(pageB);
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
