// STACK-03: the web index route renders the API status from the generated `usePlatformHealth` hook.
// The health endpoint is public and not tenant-scoped, so this journey has no cross-tenant case.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

// DESIGN-02: `/` is behind sign-in, so this runs on the dev server with the fixture session stub.
test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });
test.beforeEach(async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
});

test("index shows the API status from the generated health hook", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  const health = page.waitForResponse((response) => response.url().endsWith("/api/v1/health"));
  await page.goto("/");

  expect((await health).status()).toBe(200);
  await expect(page.getByTestId("api-health-status")).toHaveText("ok");
  expect(consoleErrors).toEqual([]);
});

test("index has no axe accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("api-health-status")).toHaveText("ok");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
