// DESIGN-04: the dev-only record detail fixture (/__fixtures/record, Vite dev server). It is public
// design scaffolding with no tenant data (its API is mocked with page.route), so there is no
// cross-tenant case.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

const API = "**/api/v1/__fixtures/record";

async function serveRecord(page: Page) {
  await page.route(API, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ summary: "Lagging cracked" }) }),
  );
}

test("record detail: tabs in the URL, 0 serious/critical axe violations", async ({ page }) => {
  await serveRecord(page);
  await page.goto("/__fixtures/record?tab=history");
  await expect(page.getByRole("tab", { name: "History" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Details" }).click();
  await expect(page).toHaveURL(/[?&]tab=details/);
  await expect(page.getByTestId("record-summary")).toHaveText("Lagging cracked");

  const results = await new AxeBuilder({ page }).include("[data-testid=record-fixture]").analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
});

test("danger confirm: focus on Cancel, Tab to Confirm, Enter confirms, toast announced then gone", async ({ page }) => {
  await serveRecord(page);
  await page.goto("/__fixtures/record");
  await page.getByRole("button", { name: "Delete", exact: true }).click();

  const dialog = page.getByRole("dialog", { name: "Delete NCR-0042?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  const blocking = (await new AxeBuilder({ page }).include("[role=dialog]").analyze()).violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(blocking).toEqual([]);

  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Delete" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();

  const toastText = page.locator("[aria-live=polite]").getByText("NCR-0042 deleted");
  await expect(toastText).toBeVisible();
  await expect(toastText).toBeHidden({ timeout: 6_000 });
});

test("ErrorState shows the correlation id; Retry re-requests and renders the data", async ({ page }) => {
  let calls = 0;
  await page.route(API, (route) => {
    calls += 1;
    return calls === 1
      ? route.fulfill({ status: 500, headers: { "X-Request-Id": "req_e2e" }, body: "" })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ summary: "Lagging cracked" }) });
  });
  await page.goto("/__fixtures/record");

  await expect(page.getByRole("alert").getByText("req_e2e")).toBeVisible();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByTestId("record-summary")).toHaveText("Lagging cracked");
  expect(calls).toBe(2);
});
