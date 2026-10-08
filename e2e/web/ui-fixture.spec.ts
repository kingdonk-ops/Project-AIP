// DESIGN-01: the dev-only component fixture (/__fixtures/ui, Vite dev server) renders every @aip/ui
// component. It is public design scaffolding with no tenant data, so there is no cross-tenant case.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { devBaseURL } from "../playwright.config";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

test("ui fixture: 0 serious/critical axe violations, IBM Plex Sans, no Google Fonts", async ({ page }) => {
  const external: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).hostname.endsWith("fonts.googleapis.com")) external.push(request.url());
  });

  await page.goto("/__fixtures/ui");
  await expect(page.getByTestId("ui-fixture")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);

  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);

  const family = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(family.replace(/["']/g, "")).toMatch(/^IBM Plex Sans/);
  expect(external).toEqual([]);
});
