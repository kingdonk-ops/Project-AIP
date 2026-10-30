// FORMS-03: the dev-only form renderer fixture (/__fixtures/form, Vite dev server) renders the coating
// ITR template with in-memory stub adapters. It is design scaffolding with no tenant data, so there is
// no cross-tenant case here: template isolation is FORMS-01's check and answer isolation INSPECTIONS-04's.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).include('[data-testid="form-fixture"]').analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

test("form renderer: conditions, fail chip, error summary and read-only, axe-clean", async ({ page }) => {
  await page.goto("/__fixtures/form");
  const fixture = page.getByTestId("form-fixture");
  await expect(fixture).toBeVisible();
  await expect(fixture.getByLabel("Remarks")).toHaveCount(0);
  await expectNoBlockingAxe(page);

  // Surface prepared: No → the remarks field appears.
  const prepared = fixture.getByRole("radiogroup", { name: "Surface prepared" });
  await prepared.getByLabel("No", { exact: true }).check();
  await expect(fixture.getByRole("textbox", { name: "Remarks" })).toBeVisible();

  // Blast standard Sa 2½.
  await fixture.getByRole("combobox", { name: "Blast standard" }).click();
  await page.getByRole("option", { name: "Sa 2½" }).click();
  await expect(fixture.getByRole("combobox", { name: "Blast standard" })).toContainText("Sa 2½");

  // DFT 0.18 mm is below 0.25 → a "Fail" chip (text, not colour only).
  await fixture.getByLabel("Average dry film thickness").fill("0.18");
  await expect(fixture.getByText("Fail", { exact: true })).toBeVisible();

  // Submit → the summary lists the unanswered required field; its link focuses the control.
  await fixture.getByRole("button", { name: "Submit" }).click();
  const summary = fixture.getByRole("alert").filter({ has: page.getByRole("heading", { name: "There is a problem" }) });
  await expect(summary).toBeVisible();
  await expect(summary.getByRole("link")).toHaveText(["Inspection date: This field is required."]);
  await expectNoBlockingAxe(page);
  await summary.getByRole("link", { name: "Inspection date: This field is required." }).click();
  await expect(fixture.getByLabel("Inspection date")).toBeFocused();

  // Answer it → the summary is gone.
  await fixture.getByLabel("Inspection date").fill("2026-10-30");
  await expect(summary).toHaveCount(0);

  // Read-only → values as text, no form controls.
  await fixture.getByRole("button", { name: "Read-only" }).click();
  const form = fixture.locator("#coating-itr");
  await expect(form.locator("input, select, button")).toHaveCount(0);
  await expect(form.getByText("Sa 2½")).toBeVisible();
  await expect(form.getByText("2026-10-30")).toBeVisible();
  await expect(form.getByText("0.18 mm")).toBeVisible();
  await expect(form.getByText("No", { exact: true })).toBeVisible();
  await expectNoBlockingAxe(page);
});
